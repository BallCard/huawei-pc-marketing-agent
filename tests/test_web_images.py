import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from PIL import Image as PILImage

from src.mvp import llm, pipeline, web_images
from src.mvp.kb import Image, LocalKB, ModelDoc

NAME = "HUAWEI MateBook X Pro 酷睿 Ultra 微绒典藏版"
PAGE = "https://consumer.huawei.com/cn/laptops/matebook-x-pro-ultra-premium-edition/"
ASSET = "https://consumer.huawei.com/content/dam/laptops/matebook-x-pro-ultra-premium-edition/images/hero/kv.jpg"
HTML = f'<title>{NAME} - 华为官网</title><h1>{NAME}</h1><img src="{ASSET}" alt="产品图">'
PASS = json.dumps(dict(kind="device", shows_device=True, usable=True, desc="浅色背景上的笔记本整机"))


class WebImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.doc = ModelDoc("model-x", NAME, "", Path(self.temp.name), sources=[dict(url=PAGE)])
        b = io.BytesIO()
        PILImage.new("RGB", (1200, 800), "white").save(b, "JPEG")
        self.image_bytes = b.getvalue()
        self.requests = []
        self.client_class = httpx.Client

        def handler(request):
            self.requests.append(str(request.url))
            if request.url.host == "www.bing.com":
                return httpx.Response(200, text="<rss><channel/></rss>")
            if str(request.url) == PAGE:
                return httpx.Response(200, text=HTML)
            if str(request.url) == ASSET:
                return httpx.Response(200, content=self.image_bytes)
            return httpx.Response(404)

        for p in (patch.object(web_images.settings, "CACHE_DIR", Path(self.temp.name)),
                  patch.object(web_images.settings, "WEB_IMAGE_SEARCH", True),
                  patch.object(web_images.httpx, "Client", side_effect=lambda **kw: self.client_class(transport=httpx.MockTransport(handler), **kw))):
            p.start()
            self.addCleanup(p.stop)

    def test_only_exact_product_page_and_product_owned_assets_are_candidates(self):
        self.assertEqual(web_images.page_candidates(HTML, PAGE, NAME), [(ASSET, "产品图")])
        for title in ("HUAWEI MateBook X Pro 2023 微绒典藏版", NAME + " 2026", "HUAWEI MateBook X Pro"):
            self.assertEqual(web_images.page_candidates(HTML.replace(NAME, title), PAGE, NAME), [])
        wrong = ASSET.replace("/laptops/matebook-x-pro-ultra-premium-edition/", "/laptops/matebook-14/")
        self.assertEqual(web_images.page_candidates(HTML.replace(ASSET, wrong), PAGE, NAME), [])
        self.assertEqual(web_images.page_candidates(HTML.replace("kv.jpg", "kv-thumb.jpg"), PAGE, NAME), [])

    def test_rejects_lookalikes_credentials_non_https_and_cross_domain_redirects(self):
        for url in ("http://consumer.huawei.com/a", "https://consumer.huawei.com.evil.test/a",
                    "https://consumer.huawei.com@evil.test/a", "https://user@consumer.huawei.com/a",
                    "https://consumer.huawei.com:8080/a", "https://127.0.0.1/a"):
            self.assertFalse(web_images.trusted_url(url, web_images.PAGE_HOSTS))
        client = self.client_class(transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "https://evil.test/image.jpg"})))
        with client, self.assertRaises(ValueError):
            web_images._fetch(client, PAGE, web_images.PAGE_HOSTS, time.monotonic() + 5, 5000)

    def test_verified_image_is_registered_served_cached_and_tamper_checked(self):
        with patch.object(web_images.llm, "describe_image", return_value=PASS) as visual:
            result = web_images.find_hero(self.doc)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(len(result["images"]), 1)
        image = result["images"][0]
        self.assertEqual(image.page, PAGE)
        self.assertEqual(image.source_type, "official_web")
        self.assertTrue(image.checked_at)
        self.assertEqual(visual.call_args.kwargs["role"], "fast")
        # Original results remain downloadable after cache freshness expires.
        kb = object.__new__(LocalKB)
        kb.load = lambda model_id: self.doc
        self.assertEqual(kb.image_file(self.doc.id, image.id), image.path)
        with patch.object(web_images.llm, "describe_image") as visual:
            self.assertEqual(web_images.find_hero(self.doc)["status"], "cached")
            visual.assert_not_called()
        image.path.write_bytes(b"corrupt")
        self.assertEqual(web_images.cached_images(self.doc), [])
        self.assertIsNone(kb.image_file(self.doc.id, image.id))
        self.assertIsNone(kb.image_file(self.doc.id, "web-../../secret.jpg"))

    def test_unverified_images_and_unsupported_vision_never_enter_registry(self):
        for verdict in (json.dumps(dict(kind="logo", shows_device=False, usable=False)),
                        json.dumps(dict(kind="device", shows_device="true", usable=True)), "[]"):
            with patch.object(web_images.llm, "describe_image", return_value=verdict):
                result = web_images.find_hero(self.doc)
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["images"], [])
        with patch.object(web_images.llm, "describe_image", side_effect=llm.LLMError("vision unavailable")):
            self.assertEqual(web_images.find_hero(self.doc)["images"], [])
        self.assertEqual(list(Path(self.temp.name).rglob("*.jpg")), [])
        self.assertEqual(list(Path(self.temp.name).rglob("verified.json")), [])

    def test_search_is_discovery_only_and_official_product_identity_still_required(self):
        self.doc.sources = []
        rss = f'<rss><channel><item><link>https://evil.test/picture</link></item><item><link>{PAGE}</link></item></channel></rss>'
        def handler(request):
            if request.url.host == "www.bing.com":
                return httpx.Response(200, text=rss)
            if str(request.url) == PAGE:
                return httpx.Response(200, text=HTML)
            if str(request.url) == ASSET:
                return httpx.Response(200, content=self.image_bytes)
            raise AssertionError("untrusted source must not be fetched")
        with patch.object(web_images.httpx, "Client", side_effect=lambda **kw: self.client_class(transport=httpx.MockTransport(handler), **kw)):
            with patch.object(web_images.llm, "describe_image", return_value=PASS):
                self.assertEqual(web_images.find_hero(self.doc)["status"], "verified")

    def test_off_switch_and_existing_local_hero_skip_network(self):
        with patch.object(web_images.settings, "WEB_IMAGE_SEARCH", False):
            self.assertEqual(web_images.find_hero(self.doc)["status"], "disabled")
        self.assertEqual(self.requests, [])
        hero = Image("local.jpg", NAME, Path("local.jpg"), "整机", PAGE, ASSET, kind="device", shows_device=True)
        self.doc.images = [hero]
        with patch.object(web_images, "find_hero") as lookup:
            result = pipeline.retrieve(SimpleNamespace(load=lambda _: self.doc), self.doc.id, {})
        lookup.assert_not_called()
        self.assertEqual(result["images"], [hero])

    def test_activity_records_follow_actual_requests_and_cached_assets_do_not_claim_network(self):
        activities = []
        with patch.object(web_images.llm, "describe_image", return_value=PASS):
            result = web_images.find_hero(self.doc, on_activity=activities.append)
        self.assertEqual(result["status"], "verified")
        self.assertTrue(any(a.get("url") == PAGE and a["status"] == "running" for a in activities))
        self.assertTrue(any(a["operation"] == "image" and a["status"] == "done" for a in activities))
        self.assertTrue(all(a.get("url") != PAGE or PAGE in self.requests for a in activities))
        self.requests.clear()
        activities.clear()
        self.assertEqual(web_images.find_hero(self.doc, on_activity=activities.append)["status"], "cached")
        self.assertEqual(self.requests, [])
        self.assertEqual([a["source_kind"] for a in activities], ["cache"])

    def test_local_retrieval_activity_is_not_reported_as_web_search(self):
        hero = Image("local.jpg", NAME, Path("local.jpg"), "整机", PAGE, ASSET, kind="device", shows_device=True)
        self.doc.images = [hero]
        activities = []
        with patch.object(web_images, "find_hero") as lookup:
            pipeline.retrieve(SimpleNamespace(load=lambda _: self.doc), self.doc.id, {}, on_activity=activities.append)
        lookup.assert_not_called()
        self.assertEqual([a["status"] for a in activities], ["running", "done"])
        self.assertTrue(all(a["source_kind"] == "knowledge" for a in activities))

    def test_network_failure_or_exhausted_lookup_budget_preserves_missing_state(self):
        with patch.object(web_images, "_fetch", side_effect=httpx.ConnectError("offline")):
            result = web_images.find_hero(self.doc)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["images"], [])
        with patch.object(web_images.llm, "remaining", return_value=5), patch.object(web_images, "_fetch") as fetch:
            result = web_images.find_hero(self.doc)
        fetch.assert_not_called()
        self.assertEqual(result["images"], [])

    def test_stale_registration_is_served_but_not_reused_for_new_drafts(self):
        with patch.object(web_images.llm, "describe_image", return_value=PASS):
            image = web_images.find_hero(self.doc)["images"][0]
        manifest = image.path.parent / "verified.json"
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        rows[0]["checked_at"] = "2020-01-01T00:00:00+00:00"
        manifest.write_text(json.dumps(rows), encoding="utf-8")
        self.assertEqual(web_images.cached_images(self.doc), [])
        self.assertEqual(web_images.cached_images(self.doc, require_fresh=False)[0].id, image.id)

    def test_verified_fallback_precedes_local_diagrams(self):
        diagram = Image("chip.jpg", NAME, Path("chip.jpg"), "芯片", PAGE, ASSET, kind="logo", shows_device=False)
        hero = Image("web.jpg", NAME, Path("web.jpg"), "整机", PAGE, ASSET, kind="device", shows_device=True)
        self.doc.images = [diagram]
        with patch.object(web_images, "find_hero", return_value=dict(images=[hero], status="verified")):
            result = pipeline.retrieve(SimpleNamespace(load=lambda _: self.doc), self.doc.id, {})
        self.assertEqual(result["images"], [hero, diagram])
        self.assertEqual(result["hero_count"], 1)
        self.assertNotIn("images", result["image_search"])


if __name__ == "__main__":
    unittest.main()

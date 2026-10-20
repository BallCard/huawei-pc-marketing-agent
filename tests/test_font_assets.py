import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.mvp import app as server


class FontAssetTests(unittest.TestCase):
    def test_login_fonts_are_public_without_exposing_the_private_api(self):
        client = TestClient(server.app)
        with patch.object(server.settings, "AUTH_PASSWORD", "font-test-only"), patch.object(server.settings, "AUTH_USERNAME", "font-test-user"):
            for path in ("/static/fonts.css", "/static/typography.css", "/static/fonts/noto-sans-sc/noto-sans-sc-latin-wght-normal.woff2", "/static/fonts/noto-sans-sc/OFL.txt"):
                self.assertEqual(client.get(path).status_code, 200, path)
            self.assertEqual(client.get("/api/info").status_code, 401)
            self.assertEqual(client.get("/img/private/example.jpg").status_code, 401)
            self.assertEqual(client.get("/login").status_code, 200)
            self.assertEqual(client.get("/static/fonts/noto-sans-sc/noto-sans-sc-latin-wght-normal.woff2").headers["content-type"], "font/woff2")

"""First-time-user walkthrough of the local studio, capturing screenshots.

Run: python -X utf8 scripts/walkthrough_roadshow.py
Output: data/ui-shots/roadshow/
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:7860"
OUT = Path("data/ui-shots/roadshow")
OUT.mkdir(parents=True, exist_ok=True)


def shot(page, name: str) -> None:
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
    print(f"[shot] {name}", flush=True)


def main() -> None:
    log: dict[str, object] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        shot(page, "01-welcome")

        page.click("#enter-studio")
        page.wait_for_timeout(1800)
        page.locator("#open-presets").click()
        page.wait_for_timeout(700)
        shot(page, "03-presets")
        presets = page.locator("#presets .preset")
        log["preset_titles"] = [presets.nth(i).inner_text() for i in range(presets.count())]
        # second preset: likely a work/commute angle, keeps the demo distinct from the earlier run
        presets.nth(1).click()
        page.wait_for_timeout(900)
        shot(page, "04-brief-filled")
        log["brief_values"] = page.evaluate(
            """() => ({
                audience: document.querySelector('#audience')?.value,
                scenario: document.querySelector('#scenario')?.value,
                product: document.querySelector('#product')?.value,
                platform: document.querySelector('#platform')?.value,
                goal: document.querySelector('#goal')?.value,
                constraints: document.querySelector('#constraints')?.value,
                extra: document.querySelector('#extra')?.value,
            })"""
        )

        started = time.time()
        page.click("#go")
        page.wait_for_timeout(2500)
        shot(page, "05-process-start")

        asked = 0
        last_shot = 0.0
        while time.time() - started < 480:
            page.wait_for_timeout(2000)
            elapsed = time.time() - started
            ask = page.locator("#agent-ask")
            if ask.is_visible():
                state = ask.get_attribute("data-state")
                if state == "asking" and asked < 2:
                    shot(page, f"06-ask-{asked + 1}")
                    asked += 1
                    log.setdefault("ask_questions", []).append(page.inner_text("#agent-ask-asking"))
                    option = page.locator("#agent-ask-options .ask-option")
                    if option.count():
                        option.first.click()
                        page.wait_for_timeout(2000)
                elif state == "done":
                    shot(page, "06-ask-done")
                    submit = page.locator("#agent-ask-done .ask-submit")
                    if submit.count() and submit.is_visible():
                        submit.click()
                        page.wait_for_timeout(3000)
                        shot(page, "05b-process-running")
            view = page.locator("#view-result")
            if view.count() and view.is_visible():
                shot(page, "07b-process-done")
                view.click()
                page.wait_for_timeout(2500)
                break
            if page.locator("#stage").is_visible():
                break
            if elapsed - last_shot > 25:
                last_shot = elapsed
                shot(page, f"07-process-{int(elapsed):03d}")
        log["elapsed_to_result"] = int(time.time() - started)
        page.wait_for_timeout(2500)
        shot(page, "08-work")

        if page.locator('[data-preview-device="mobile"]').is_visible():
            page.click('[data-preview-device="mobile"]')
            page.wait_for_timeout(1500)
            shot(page, "09-work-mobile")
            page.click('[data-preview-device="desktop"]')
            page.wait_for_timeout(1000)
        log["work_text"] = page.inner_text("#stage")[:8000]
        log["notice"] = page.inner_text("#notice") if page.locator("#notice").count() else ""
        log["summary"] = page.inner_text("#creative-summary") if page.locator("#creative-summary").count() else ""

        # try another platform quickly via brief re-submit is expensive; skip

        page.click("#tab-evidence")
        page.wait_for_timeout(1500)
        shot(page, "10-evidence")
        log["evidence_text"] = page.inner_text("#page-evidence")[:10000]
        for tab in ("judge", "verify"):
            btn = page.locator(f"#insight-tab-{tab}")
            if btn.count() and btn.is_visible():
                btn.click()
                page.wait_for_timeout(1200)
                shot(page, f"11-evidence-{tab}")
                log[f"evidence_{tab}"] = page.inner_text(f"#insight-{tab}")[:8000]

        page.click("#tab-work")
        page.wait_for_timeout(800)
        log["refine_visible"] = page.locator("#revise").is_visible()
        log["review_status"] = page.inner_text("#work-review-status") if page.locator("#work-review-status").count() else ""
        page.click("#tab-create")
        page.wait_for_timeout(800)
        shot(page, "12-create-after")

        browser.close()

    (OUT / "walkthrough.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE", json.dumps({k: v for k, v in log.items() if k in ("elapsed_to_result", "preset_titles", "ask_questions")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

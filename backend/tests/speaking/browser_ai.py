"""Local UI checks for AI features. Provider responses are mocked; no audio leaves localhost."""

import json
import os
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[3]
BASE = os.getenv("SPEAKING_TEST_BASE", "http://127.0.0.1:8010")


def main():
    sample = httpx.get(BASE + "/api/samples/sample-01").json()
    fake = {**sample, "source": "live", "question": {"id": "study-1", "text": "Do you work or are you a student?"}, "pronunciation": {
        "status": "assessed", "scores": {"accuracy": 83, "fluency": 75, "prosody": 71, "pronunciation": 78},
        "segments": [{"recognized_text": "Separate acoustic transcript", "words": [{"word": "school", "accuracy": 62,
            "start_s": .1, "end_s": .3, "error_type": "Mispronunciation", "phonemes": [{"phoneme": "s", "accuracy": 60}]}]}]}}
    errors, uploads = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE)
        expect(page.locator("#pronunciation-consent")).to_be_disabled()
        expect(page.locator("#pronunciation-consent")).not_to_be_checked()

        def configured(route):
            response = route.fetch()
            data = response.json()
            data["pronunciation"]["configured"] = True
            route.fulfill(response=response, json=data)
        page.route("**/api/health", configured)
        page.reload()
        expect(page.locator("#pronunciation-consent")).to_be_enabled()
        expect(page.locator("#pronunciation-consent")).not_to_be_checked()

        def transcribe(route):
            uploads.append(route.request.post_data_buffer)
            route.fulfill(json=fake)
        page.route("**/api/transcribe", transcribe)
        page.locator("#audio-file").set_input_files(FIXTURES / "sample-01.m4a")
        page.locator("#pronunciation-consent").check()
        page.locator("#submit").click()
        expect(page.locator("#pronunciation-result")).to_contain_text("83/100")
        expect(page.locator("#pronunciation-result")).to_contain_text("Chưa hiệu chỉnh band IELTS")
        assert b'pronunciation_consent' in uploads[0] and b'true' in uploads[0]
        assert "Separate acoustic transcript" not in page.locator("#transcript").inner_text()
        page.locator("#pronunciation-result summary").click()
        expect(page.locator("#pronunciation-result")).to_contain_text("school: 62/100")
        page.locator("#rubric-criterion").select_option("PR")
        page.locator("#rubric-query").fill("stress rhythm intonation intelligibility")
        page.locator("#rubric-form button").click()
        expect(page.locator("#rubric-results details")).to_have_count(4)
        assert page.locator("#rubric-results a").first.get_attribute("href").startswith("https://ielts.org/")
        page.locator("#rubric-results summary").first.click()
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=ROOT / f"speaking/qa/ai-feedback-{width}.png", full_page=True)
        page.goto(BASE + "/exam")
        expect(page.locator("#start-exam")).to_be_enabled()
        expect(page.locator("#exam-pronunciation-consent")).to_be_disabled()
        page.locator("#rubric-form button").click()
        expect(page.locator("#rubric-results details")).to_have_count(4)
        assert not errors, errors
        browser.close()
    print(json.dumps({"status": "ok", "provider_calls": 0, "mocked_uploads": len(uploads), "page_errors": errors}))


if __name__ == "__main__":
    main()

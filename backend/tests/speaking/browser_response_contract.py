"""Regression checks for undefined.length; all malformed API responses are local stubs."""

import os
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
import httpx
from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("SPEAKING_TEST_BASE", "http://127.0.0.1:8010")


def main():
    sample = httpx.get(BASE + "/api/samples/sample-01").json()
    sample["metrics"].pop("adjacent_repetitions", None)
    sample["metrics"]["disfluency_candidates"] = {}
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/samples/sample-01?*", lambda route: route.fulfill(json=sample))
        page.goto(BASE)
        expect(page.locator(".topic-button")).to_have_count(3)
        page.locator(".sample-library summary").click()
        page.locator("#sample-select").select_option("sample-01")
        page.locator("#load-sample").click()
        expect(page.locator("#transcript")).to_contain_text(sample["transcript"].split()[0])
        for label in ("Lặp từ liền nhau", "Lặp cụm nhận dạng", "Dấu hiệu tự sửa"):
            expect(page.locator(".metric").filter(has_text=label).locator("strong")).to_have_text("—")
        expect(page.locator("#error")).to_be_hidden()
        # Exercise the exact path reported by the user: submit a recording on /.
        # Keep external STT/assessment completely stubbed.
        live = {**sample, "source": "live", "question": {"id": "study-1", "part": 1,
                "text": "Do you work or are you a student?"}}
        page.route("**/api/transcribe", lambda route: route.fulfill(json=live))
        page.locator("#next").click()
        page.locator("#prev").click()
        page.locator("#audio-file").set_input_files(FIXTURES / "sample-01.m4a")
        page.locator("#submit").click()
        expect(page.locator("#session-count")).to_have_text("1")
        expect(page.locator("#history tr")).to_have_count(1)
        expect(page.locator("#error")).to_be_hidden()
        for label in ("Lặp từ liền nhau", "Lặp cụm nhận dạng", "Dấu hiệu tự sửa"):
            expect(page.locator(".metric").filter(has_text=label).locator("strong")).to_have_text("—")
        page.route("**/api/speaking/rubric/search", lambda route: route.fulfill(json={"status": "ok"}))
        page.locator("#rubric-form button").click()
        expect(page.locator("#rubric-results")).to_contain_text("thiếu danh sách chunks")
        page.on("dialog", lambda dialog: dialog.accept())
        page.goto(BASE + "/exam")
        expect(page.locator("#start-exam")).to_be_enabled()
        page.route("**/api/exam/sessions", lambda route: route.fulfill(json={"session": {"turns": []}, "answers": []}))
        page.locator("#start-exam").click()
        expect(page.locator("#exam-error")).to_contain_text("thiếu speaking_turns hoặc answers")
        expect(page.locator("#setup")).to_be_visible()
        assert page.evaluate("localStorage.getItem('speaking-exam-session')") is None
        assert not errors, errors
        browser.close()
    print("Response contract regression passed: missing metrics stay unknown; malformed rubric/session show clear errors; no provider calls.")


if __name__ == "__main__":
    main()

"""Local browser QA. Successful live responses are stubbed; no Groq calls."""

from .fixtures_audio import audio_fixture
import json
import os
from email.parser import BytesParser
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "backend" / "ielts_agent" / "agents" / "speaking" / "qa"
BASE = os.environ.get("SPEAKING_TEST_BASE", "http://127.0.0.1:8000")


def no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal page overflow"


def main():
    OUTPUT.mkdir(exist_ok=True)
    saved = httpx.get(f"{BASE}/api/samples/sample-01").json()
    live = {**saved, "source": "live", "question": {"id": "study-1", "text": "Do you work or are you a student?"}}
    live.pop("sample", None)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, permissions=["microphone"], accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE)
        expect(page.locator(".topic-button")).to_have_count(3)
        expect(page.get_by_role("button", name="Bắt đầu ghi âm", exact=True)).to_be_enabled()
        assert page.locator("svg.lucide").count() > 10
        no_overflow(page)
        page.screenshot(path=OUTPUT / "desktop-ready.png", full_page=True)

        page.locator(".sample-library summary").click()
        page.locator("#sample-select").select_option("sample-06")
        page.locator("#sample-fillers").check()
        page.get_by_role("button", name="Mở kết quả mẫu", exact=True).click()
        expect(page.locator("#result-tag")).to_have_text("Cần kiểm tra")
        expect(page.locator("#quality-warnings")).to_contain_text("vượt ngoài thời lượng audio")
        page.locator("#metrics-comparison summary").click()
        expect(page.locator(".stt-comparison .unavailable")).to_have_count(4)
        expect(page.locator("#vad-details")).to_be_visible()
        expect(page.locator("#session-count")).to_have_text("0")
        page.screenshot(path=OUTPUT / "desktop-warning.png", full_page=True)

        page.locator("#sample-select").select_option("sample-01")
        page.locator("#sample-fillers").uncheck()
        page.get_by_role("button", name="Mở kết quả mẫu", exact=True).click()
        expect(page.locator("#result-source")).to_contain_text("sample-01")
        expect(page.locator("#result-tag")).to_have_text("Đã nhận transcript")
        expect(page.locator("#transcript .word")).to_have_count(len(saved["words"]))
        with page.expect_download() as downloading:
            page.get_by_role("button", name="Tải audio", exact=True).click()
        assert downloading.value.suggested_filename == "sample-01.m4a"
        assert Path(downloading.value.path()).read_bytes() == audio_fixture("sample-01.m4a")
        page.locator("#transcript .word").first.click()
        expect(page.locator("#playback")).to_have_js_property("paused", False)
        page.locator("#playback").evaluate("audio => audio.pause()")
        page.screenshot(path=OUTPUT / "desktop-result.png", full_page=True)

        page.get_by_role("button", name="Câu tiếp theo", exact=True).click()
        expect(page.locator("#question-number")).to_have_text("02")
        page.get_by_role("button", name="Câu trước", exact=True).click()
        page.get_by_role("button", name="Bắt đầu ghi âm", exact=True).click()
        expect(page.locator("#record-status")).to_have_text("Đang ghi âm")
        expect(page.locator("#timer")).to_have_text("00:01", timeout=10000)
        assert page.locator("#next").is_disabled()
        assert page.evaluate("document.querySelector('#waveform').getContext('2d').getImageData(0,0,200,50).data.some((v,i)=>i%4===3 && v>0)")
        page.screenshot(path=OUTPUT / "desktop-recording.png", full_page=True)
        page.get_by_role("button", name="Dừng ghi âm", exact=True).click()
        expect(page.locator("#record-status")).to_have_text("Bản thu sẵn sàng")
        expect(page.locator("#submit")).to_be_enabled()
        expect(page.locator("#playback")).to_have_js_property("readyState", 4, timeout=10000)

        page.locator("#audio-file").set_input_files(FIXTURES / "sample-01.m4a")
        expect(page.locator("#audio-name")).to_have_text("sample-01.m4a")
        with page.expect_download() as downloading:
            page.get_by_role("button", name="Tải audio", exact=True).click()
        assert Path(downloading.value.path()).read_bytes() == audio_fixture("sample-01.m4a")
        page.get_by_role("button", name="Câu tiếp theo", exact=True).click()
        page.get_by_role("button", name="Câu trước", exact=True).click()
        expect(page.locator("#audio-name")).to_have_text("sample-01.m4a")
        if not httpx.get(f"{BASE}/api/health").json()["groq_configured"]:
            page.get_by_role("button", name="Gửi câu trả lời", exact=True).click()
            expect(page.locator("#error")).to_contain_text("GROQ_API_KEY", timeout=10000)
            expect(page.locator("#submit")).to_be_enabled()

        page.route("**/api/transcribe", lambda route: route.fulfill(json=live))
        page.get_by_role("button", name="Gửi câu trả lời", exact=True).click()
        expect(page.locator("#session-count")).to_have_text("1")
        expect(page.locator("#history-table-wrap")).to_be_visible()
        expect(page.locator("#result-source")).to_contain_text("study-1")
        with page.expect_download() as downloading:
            page.get_by_role("button", name="Tải audio", exact=True).click()
        assert downloading.value.suggested_filename.startswith("study-1-")
        assert downloading.value.suggested_filename.endswith(".m4a")
        assert Path(downloading.value.path()).read_bytes() == audio_fixture("sample-01.m4a")
        with page.expect_download() as downloading:
            page.get_by_role("button", name="Xuất kết quả", exact=True).click()
        download = downloading.value
        exported = json.loads(Path(download.path()).read_text())
        assert len(exported["tables"]["ANSWER"]) == 1
        assert exported["tables"]["ATTEMPT"][0]["audio_uri"] is None
        assert "GROQ_API_KEY" not in json.dumps(exported)
        page.get_by_role("button", name="Phiên mới", exact=True).click()
        page.get_by_role("button", name="Hủy", exact=True).click()
        expect(page.locator("#session-count")).to_have_text("1")
        page.get_by_role("button", name="Phiên mới", exact=True).click()
        page.get_by_role("button", name="Bắt đầu phiên mới", exact=True).click()
        expect(page.locator("#session-count")).to_have_text("0")

        cues = httpx.get(f"{BASE}/api/cue-cards").json()["cards"]
        question_map = {card["id"]: card for card in cues}
        question_map.update({q["id"]: q for topic in httpx.get(f"{BASE}/api/questions").json()["topics"] for q in topic["questions"]})
        submissions = []

        def stub_submission(route):
            content_type = route.request.headers["content-type"]
            message = BytesParser().parsebytes(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + route.request.post_data_buffer)
            fields = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True).decode()
                      for part in message.get_payload() if not part.get_filename()}
            submissions.append(fields)
            question = question_map[fields["question_id"]]
            response = {**saved, "schema_version": "1.1", "source": "live", "part": question.get("part", 1), "question": question}
            response.pop("sample", None)
            if response["part"] == 2:
                response["preparation"] = {"seconds": float(fields["preparation_seconds"]), "notes": fields["notes"], "limit_seconds": 60}
                response["speaking_limit_seconds"] = 120
            route.fulfill(json=response)

        part2 = context.new_page()
        part2.on("pageerror", lambda error: errors.append(str(error)))
        part2.clock.install()
        part2.route("**/api/transcribe", stub_submission)
        part2.goto(BASE)
        expect(part2.get_by_role("tab", name="Part 2", exact=True)).to_be_enabled()
        part2.get_by_role("tab", name="Part 2", exact=True).click()
        expect(part2.locator("#cue-points li")).to_have_count(3)
        expect(part2.locator("#question-counter")).to_have_text("01 / 06")
        part2.locator("#prep-notes").fill("learned programming; group project; useful at university")
        part2.get_by_role("button", name="Chuẩn bị 1 phút", exact=True).click()
        expect(part2.locator("#part2-status")).to_have_text("Đang chuẩn bị")
        part2.clock.fast_forward(30000)
        expect(part2.locator("#prep-timer")).to_have_text("00:30")
        expect(part2.get_by_role("tab", name="Part 1", exact=True)).to_be_disabled()
        expect(part2.locator("#prep-notes")).to_be_enabled()
        no_overflow(part2)
        part2.screenshot(path=OUTPUT / "part2-desktop-preparation.png", full_page=True)
        part2.get_by_role("button", name="Hủy chuẩn bị", exact=True).click()
        expect(part2.locator("#part2-status")).to_have_text("Sẵn sàng")
        expect(part2.locator("#prep-timer")).to_have_text("01:00")
        assert part2.evaluate("state.stream === null")

        part2.get_by_role("button", name="Chuẩn bị 1 phút", exact=True).click()
        expect(part2.locator("#part2-status")).to_have_text("Đang chuẩn bị")
        part2.clock.fast_forward(60000)
        expect(part2.locator("#part2-status")).to_have_text("Đang nói")
        expect(part2.locator("#prep-timer")).to_have_text("00:00")
        expect(part2.locator("#speaking-timer")).to_have_text("02:00")
        expect(part2.locator("#prep-notes")).to_be_disabled()
        part2.screenshot(path=OUTPUT / "part2-desktop-recording.png", full_page=True)
        part2.clock.fast_forward(119000)
        expect(part2.locator("#speaking-timer")).to_have_text("00:01")
        part2.clock.fast_forward(1000)
        expect(part2.locator("#part2-status")).to_have_text("Đã thu âm")
        expect(part2.locator("#speaking-timer")).to_have_text("00:00")
        expect(part2.locator("#submit")).to_be_enabled()
        part2.get_by_role("button", name="Gửi câu trả lời", exact=True).click()
        expect(part2.locator("#session-count")).to_have_text("1")
        assert float(submissions[-1]["preparation_seconds"]) == 60
        assert "group project" in submissions[-1]["notes"]

        part2.get_by_role("button", name="Câu tiếp theo", exact=True).click()
        part2.locator("#prep-notes").fill("Da Nang; beach; friends")
        part2.get_by_role("button", name="Chuẩn bị 1 phút", exact=True).click()
        expect(part2.locator("#part2-status")).to_have_text("Đang chuẩn bị")
        part2.clock.fast_forward(20000)
        part2.get_by_role("button", name="Bắt đầu nói", exact=True).click()
        expect(part2.locator("#part2-status")).to_have_text("Đang nói")
        part2.clock.fast_forward(2000)
        part2.get_by_role("button", name="Dừng ghi âm", exact=True).click()
        expect(part2.locator("#part2-status")).to_have_text("Đã thu âm")
        part2.get_by_role("button", name="Gửi câu trả lời", exact=True).click()
        expect(part2.locator("#session-count")).to_have_text("2")
        assert 20 <= float(submissions[-1]["preparation_seconds"]) <= 20.5

        part2.get_by_role("tab", name="Part 1", exact=True).click()
        part2.locator("#audio-file").set_input_files(FIXTURES / "sample-01.m4a")
        part2.get_by_role("button", name="Gửi câu trả lời", exact=True).click()
        expect(part2.locator("#session-count")).to_have_text("3")
        part2.get_by_role("button", name="Xem câu trả lời part2-skill", exact=True).click()
        expect(part2.get_by_role("tab", name="Part 2", exact=True)).to_have_attribute("aria-selected", "true")
        expect(part2.locator("#result-source")).to_contain_text("part2-skill")
        with part2.expect_download() as downloading:
            part2.get_by_role("button", name="Xuất kết quả", exact=True).click()
        exported = json.loads(Path(downloading.value.path()).read_text())
        assert {t["part"] for t in exported["tables"]["SPEAKING_TURN"]} == {"part1", "part2"}
        assert exported["extensions"]["analysis"][0]["analysis"]["preparation"]["seconds"] == 60
        assert len(exported["tables"]["CONTENT_ITEM"][0]["body"]["questions"][0]["points"]) == 3
        part2.set_viewport_size({"width": 390, "height": 844})
        no_overflow(part2)
        part2.screenshot(path=OUTPUT / "part2-mobile-result.png", full_page=True)
        part2.set_viewport_size({"width": 320, "height": 740})
        no_overflow(part2)

        mobile = context.new_page()
        mobile.set_viewport_size({"width": 390, "height": 844})
        mobile.on("pageerror", lambda error: errors.append(str(error)))
        mobile.goto(BASE)
        expect(mobile.locator(".topic-button")).to_have_count(3)
        no_overflow(mobile)
        mobile.screenshot(path=OUTPUT / "mobile-ready.png", full_page=True)
        mobile.locator(".sample-library summary").click()
        mobile.locator("#sample-select").select_option("sample-06")
        mobile.locator("#sample-fillers").check()
        mobile.get_by_role("button", name="Mở kết quả mẫu", exact=True).click()
        expect(mobile.locator("#quality-warnings")).to_contain_text("vượt ngoài thời lượng audio")
        no_overflow(mobile)
        mobile.screenshot(path=OUTPUT / "mobile-warning.png", full_page=True)
        mobile.set_viewport_size({"width": 320, "height": 740})
        no_overflow(mobile)

        denied = context.new_page()
        denied.add_init_script("navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied', 'NotAllowedError'); }")
        denied.goto(BASE)
        expect(denied.locator(".topic-button")).to_have_count(3)
        denied.get_by_role("button", name="Bắt đầu ghi âm", exact=True).click()
        expect(denied.locator("#error")).to_contain_text("Chưa được cấp quyền microphone")
        expect(denied.locator("#upload")).to_be_enabled()
        assert not errors, errors
        browser.close()
    print("Browser QA passed: Parts 1/2, desktop/mobile, preparation countdown, automatic recording/stop, early start, cancellation, notes, playback, validation, mixed session export and reset. No live Groq calls.")


if __name__ == "__main__":
    main()

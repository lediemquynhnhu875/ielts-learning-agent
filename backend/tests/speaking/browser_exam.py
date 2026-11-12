"""UI QA for the local exam. Uses real text endpoints; never calls Groq."""

import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


BASE = os.environ.get("SPEAKING_TEST_BASE", "http://127.0.0.1:8010")
OUTPUT = Path(__file__).resolve().parents[3] / "backend/ielts_agent/agents/speaking/qa"
ANSWER = "I learned programming at university because it helps me solve difficult problems with my friends."


def stub_review_flow(page):
    """Teacher review and weakness panels on stubbed grading responses.

    The real grader is a paid, rate-limited call, so the UI contract is checked
    against fixtures here; speaking/grading.py itself is covered by unit tests.
    """
    quote = ANSWER[ANSWER.index("difficult problems"):ANSWER.index("difficult problems") + 18]
    criteria = [{"criterion": c, "status": "insufficient_evidence", "band": None,
                 "comment": f"{c} chờ giáo viên", "descriptor_refs": [],
                 "evidence": [{"quote": quote}], "grader_bands": {"A": 5, "B": 6}}
                for c in ("FC", "LR", "GRA")]
    criteria.append({"criterion": "PR", "status": "not_assessed", "band": None,
                     "comment": "Chưa có feedback âm thanh Azure cho phiên này.",
                     "descriptor_refs": [], "evidence": []})
    pending = {"status": "pending_teacher", "overall_band": None, "criteria": criteria,
               "corrections": [], "limitations": "Fixture", "disclaimer": "Fixture",
               "grading_errors": ["UC03: grader disagreement ≥1.0; teacher reconciliation required"],
               "descriptor_sources": []}
    final = {**pending, "status": "final", "overall_band": 5.5,
             "criteria": [{**row, "band": None if row["criterion"] == "PR" else 5.5,
                           "status": "not_assessed" if row["criterion"] == "PR" else "assessed"}
                          for row in criteria],
             "grading_errors": []}
    profile = {"status": "ready", "weakest_criteria": ["LR"], "not_assessed": ["PR"],
               "criteria": [{"criterion": "LR", "band": 5.5, "rank": 1, "comment": "c",
                             "descriptor_refs": [], "evidence": [{"turn_number": 2, "quote": quote}],
                             "next_band_descriptor": {"band": 6, "chunk_id": "lr-6", "text": "Rubric band 6 text"}}],
               "recurring_flags": [], "corrections": [], "write_target": None}
    page.route("**/assessment", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"assessment": pending, "graders": [], "retryable": False, "rag": {}})))
    page.route("**/teacher-review", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"assessment": final, "teacher_review": {"bands": {"FC": 5.5}}})))
    page.route("**/weakness-profile", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(profile)))

    page.get_by_role("button", name="Chạy hai giám khảo", exact=True).click()
    expect(page.locator("#assessment-status")).to_have_text("Cần giáo viên xem lại")
    expect(page.locator("#teacher-panel")).to_be_visible()
    expect(page.locator(".grader-split").first).to_have_text("A 5 · B 6")
    expect(page.locator("#teacher-bands")).to_be_hidden()
    page.locator("#teacher-action").select_option("edit")
    expect(page.locator("#teacher-bands")).to_be_visible()
    expect(page.locator("#teacher-band-grid input")).to_have_count(4)
    page.locator("#teacher-id").fill("11111111-1111-1111-1111-111111111111")
    page.locator("#teacher-band-FC").fill("5.5")
    page.get_by_role("button", name="Gửi quyết định của giáo viên", exact=True).click()
    expect(page.locator("#assessment-status")).to_have_text("Giáo viên đã chốt")
    expect(page.locator("#overall")).to_contain_text("5.5")
    expect(page.locator("#teacher-panel")).to_be_hidden()
    page.get_by_role("button", name="Hồ sơ điểm yếu", exact=True).click()
    expect(page.locator("#weakness-panel")).to_be_visible()
    expect(page.locator(".weakness-row h4")).to_have_text("#1 LR · band 5.5")
    expect(page.locator(".weakness-row .muted")).to_contain_text("Rubric band 6 text")
    page.unroute("**/assessment")
    page.unroute("**/teacher-review")
    page.unroute("**/weakness-profile")


def main():
    OUTPUT.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, permissions=["microphone"], accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/exam")
        expect(page.locator("#exam-topic option")).to_have_count(6)
        # The mock exam records; the typed flow below is explicitly a practice session.
        expect(page.locator("#exam-mode")).to_have_value("voice")
        expect(page.locator("#save-audio")).to_be_enabled()
        page.screenshot(path=OUTPUT / "exam-setup-desktop.png", full_page=True)
        page.locator("#exam-mode").select_option("text")
        expect(page.locator("#save-audio")).to_be_disabled()
        page.get_by_role("button", name="Bắt đầu thi thử →", exact=True).click()
        expect(page.locator("#session-mode")).to_contain_text("Luyện tập · gõ chữ")
        expect(page.locator("#exam-part")).to_contain_text("PART1")
        page.get_by_role("button", name="Yêu cầu xem trước Part 3", exact=True).click()
        expect(page.locator("#exam-notice")).to_contain_text("Không xem trước")
        page.get_by_role("button", name="Tạm dừng", exact=True).click()
        expect(page.locator("#exam-text")).to_be_disabled()
        # A paused session disables every control, so it has to say why and offer the way out.
        expect(page.locator("#paused-banner")).to_be_visible()
        page.reload()
        expect(page.get_by_role("button", name="Tiếp tục phiên", exact=True)).to_be_visible()
        expect(page.locator("#paused-banner")).to_be_visible()
        page.get_by_role("button", name="Tiếp tục làm bài", exact=True).click()
        expect(page.locator("#paused-banner")).to_be_hidden()
        expect(page.locator("#exam-text")).to_be_enabled()
        for i in range(10):
            if i == 4:
                expect(page.locator("#exam-preparation")).to_be_visible()
                expect(page.locator("#exam-cue li")).to_have_count(3)
                page.get_by_role("button", name="Chuẩn bị 1 phút", exact=True).click()
                expect(page.locator("#phase-label")).to_have_text("Chuẩn bị")
                page.get_by_role("button", name="Bắt đầu nói", exact=True).click()
                expect(page.locator("#phase-label")).to_contain_text("text")
            if i == 7:
                expect(page.locator("#exam-grounding")).to_be_visible()
                page.screenshot(path=OUTPUT / "exam-part3-desktop.png", full_page=True)
            page.locator("#exam-text").fill(ANSWER)
            page.get_by_role("button", name="Gửi câu trả lời →", exact=True).click()
            expect(page.locator("#exam-history > li")).to_have_count(i + 1)
        expect(page.locator("#exam-result")).to_be_visible()
        expect(page.locator("#overall")).to_have_text("Chưa có điểm tổng")
        with page.expect_download() as downloaded:
            page.get_by_role("button", name="Xuất JSON", exact=True).click()
        data = json.loads(Path(downloaded.value.path()).read_text())
        assert len(data["tables"]["ANSWER"]) == 10
        assert data["tables"]["SESSION"][0]["status"] == "finished"
        assert all(a["duration_s"] is None for a in data["tables"]["SPEAKING_TURN"])
        stub_review_flow(page)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=OUTPUT / "exam-result-mobile.png", full_page=True)
        page.screenshot(path=OUTPUT / "exam-teacher-review-mobile.png", full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="Tạo phiên khác", exact=True).click()
        page.locator("#exam-mode").select_option("voice")
        page.get_by_role("button", name="Bắt đầu thi thử →", exact=True).click()
        expect(page.locator("#session-mode")).to_contain_text("Thi thử · ghi âm")
        expect(page.locator("#voice-answer")).to_be_visible()
        expect(page.locator("#text-answer")).to_be_hidden()
        # Leaving a session mid-way must not require finishing it first.
        page.get_by_role("button", name="Bắt đầu phiên mới", exact=True).click()
        expect(page.locator("#setup")).to_be_visible()
        expect(page.locator("#exam-mode")).to_have_value("voice")
        page.get_by_role("button", name="Bắt đầu thi thử →", exact=True).click()
        expect(page.locator("#voice-answer")).to_be_visible()
        page.get_by_role("button", name="Bắt đầu ghi âm", exact=True).click()
        expect(page.get_by_role("button", name="Dừng ghi âm", exact=True)).to_be_visible()
        page.get_by_role("button", name="Dừng ghi âm", exact=True).click()
        expect(page.locator("#exam-playback")).to_be_visible()
        expect(page.get_by_role("button", name="Gửi câu trả lời →", exact=True)).to_be_enabled()
        # Deliberately do not upload fake microphone audio to Groq.
        assert not errors, errors
        browser.close()
    print("Exam browser checks passed: voice-only mock default, typed practice 3-part flow, "
          "pause/reload/resume, Part 2 phase, "
          "grounded Part 3, export, stubbed teacher review and weakness profile, mobile and "
          "microphone recording. No Groq calls.")


if __name__ == "__main__":
    main()

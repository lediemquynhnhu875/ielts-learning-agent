"""Bộ sinh dữ liệu Speaking: hạn mức token, validator, lắp ráp và metric.

Không test nào ở đây gọi LLM. Mọi thứ cần mạng đều được thay bằng stub, nên
suite chạy được trong CI và không tốn quota Groq.
"""

from datetime import datetime, timedelta, timezone
import json
import random
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
SYNTH = ROOT / "backend" / "ielts_agent" / "agents" / "speaking" / "synth"
sys.path.insert(0, str(SYNTH))

import assemble          # noqa: E402
import jobs              # noqa: E402
import plan as planner   # noqa: E402
import prompts           # noqa: E402
import qbank             # noqa: E402
import report            # noqa: E402
import validate as v     # noqa: E402


class PromptLibraryTests(unittest.TestCase):
    def test_every_prompt_has_version_temperature_and_cap(self):
        for prompt_id in prompts.TEMPLATES:
            self.assertIn(prompt_id, prompts.VERSIONS)
            self.assertIn(prompt_id, prompts.TEMPERATURES)
            self.assertIn(prompt_id, prompts.MAX_TOKENS)

    def test_no_cap_can_breach_the_output_limit(self):
        """OTPM là 1.000 token đầu ra mỗi phút, nên mọi cap phải nằm dưới mức đó."""
        limit = planner.load_spec()["limits"]["output_tokens_per_minute"]
        for prompt_id, cap in prompts.MAX_TOKENS.items():
            self.assertLess(cap, limit, prompt_id)

    def test_unfilled_placeholder_raises_instead_of_leaking(self):
        with self.assertRaises(KeyError):
            prompts.render("P6b", {})


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mktemp(suffix=".sqlite3")
        self.db = jobs.connect(self.path)
        self.budget = jobs.Budget(self.db, 8000, 200000, 1000)

    def tearDown(self):
        self.db.close()
        Path(self.path).unlink(missing_ok=True)

    def test_output_limit_blocks_a_second_large_call(self):
        self.budget.settle(self.budget.wait_for("m", 1700, 900), 1500, 750)
        self.assertGreater(self.budget.headroom("m", 1700, 900), 50)
        # Một lệnh nhỏ vẫn lọt, vì chỉ còn 250 token đầu ra trong cửa sổ.
        self.assertEqual(self.budget.headroom("m", 1700, 200), 0.0)

    def test_wait_is_measured_from_the_reservation_not_the_clock_minute(self):
        """Reservation đặt giữa phút chỉ rời cửa sổ 60 giây sau đó."""
        self.budget.settle(self.budget.wait_for("m", 1700, 900), 1500, 900)
        wait = self.budget.headroom("m", 1700, 900)
        self.assertGreater(wait, 55)
        self.assertLess(wait, 62)

    def test_daily_limit_stops_the_run_with_a_clear_message(self):
        budget = jobs.Budget(self.db, 8000, 3000, 1000)
        budget.settle(budget.wait_for("m", 2000, 500), 2000, 500)
        with self.assertRaises(RuntimeError) as caught:
            budget.check_day("m", 2000)
        self.assertIn("token hôm nay", str(caught.exception))

    def test_model_priority_follows_the_candidate_order(self):
        """Phá thế hoà bằng tên model thì model đầu bảng chữ cái luôn thắng."""
        self.assertEqual(jobs.pick_model(self.budget, ["zz", "aa"], 1700, 900), "zz")

    def test_a_busy_model_yields_to_the_next_candidate(self):
        self.budget.settle(self.budget.wait_for("zz", 1700, 900), 1500, 900)
        self.assertEqual(jobs.pick_model(self.budget, ["zz", "aa"], 1700, 900), "aa")

    def test_reasoning_models_get_a_low_effort_so_json_is_not_truncated(self):
        self.assertEqual(jobs.model_kwargs("openai/gpt-oss-120b"),
                         {"reasoning_effort": "low"})
        self.assertEqual(jobs.model_kwargs("qwen/qwen3.8-27b"), {})


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mktemp(suffix=".sqlite3")
        self.db = jobs.connect(self.path)

    def tearDown(self):
        self.db.close()
        Path(self.path).unlink(missing_ok=True)

    def test_same_prompt_input_and_seed_is_one_job(self):
        first = jobs.enqueue(self.db, "P6b", {"turn_text": "a"}, 1, "m")
        again = jobs.enqueue(self.db, "P6b", {"turn_text": "a"}, 1, "m")
        other = jobs.enqueue(self.db, "P6b", {"turn_text": "a"}, 2, "m")
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertEqual(len(jobs.pending(self.db)), 2)

    def test_json_survives_code_fences_and_surrounding_prose(self):
        self.assertEqual(jobs.parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(jobs.parse_json('Sure! {"b": [1, 2]} hope that helps'),
                         {"b": [1, 2]})
        with self.assertRaises(ValueError):
            jobs.parse_json("no json at all")

    def test_a_finished_job_is_never_called_again(self):
        jid = jobs.enqueue(self.db, "P6b", {"turn_text": "a"}, 1, "m")
        self.db.execute(
            "UPDATE gen_job SET status='ok', output_json=? WHERE job_id=?",
            (json.dumps({"points": ["x"]}), jid))
        self.db.commit()
        row = self.db.execute("SELECT * FROM gen_job WHERE job_id=?", (jid,)).fetchone()
        calls = []

        def explode(*args, **kwargs):
            calls.append(1)
            raise AssertionError("không được gọi lại job đã ok")

        result = jobs.run(self.db, row, None, v.check,
                          SimpleNamespace(chat=SimpleNamespace(
                              completions=SimpleNamespace(create=explode))))
        self.assertEqual(result, {"points": ["x"]})
        self.assertEqual(calls, [])

    def test_validator_feedback_is_sent_back_and_the_retry_is_accepted(self):
        """Mẫu hỏng quay lại model kèm danh sách lỗi, đúng mục 8.4."""
        payload = {"_part1_questions": ["Do you work?"],
                   "_bounds": {"part1": [25, 40]}, "topic": "x",
                   "part1_script": "1. Do you work?", "part1_words": "25-40",
                   "age": 20, "years": 5, "weakness_list": "articles",
                   "speaking_profile": "p", "errors_per_100": "4-6"}
        jid = jobs.enqueue(self.db, "P6a1", payload, 1, "m")
        row = self.db.execute("SELECT * FROM gen_job WHERE job_id=?", (jid,)).fetchone()
        good = {"turns": [{"role": "examiner", "text": "Do you work?"},
                          {"role": "candidate", "text": " ".join(["word"] * 30)}]}
        bad = {"turns": [{"role": "examiner", "text": "Where do you live?"},
                         {"role": "candidate", "text": " ".join(["word"] * 30)}]}
        sent = []

        def fake_create(**kwargs):
            sent.append(kwargs["messages"][-1]["content"])
            body = bad if len(sent) == 1 else good
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content=json.dumps(body)))],
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=200))

        budget = jobs.Budget(self.db, 8000, 200000, 1000)
        result = jobs.run(self.db, row, budget, v.check,
                          SimpleNamespace(chat=SimpleNamespace(
                              completions=SimpleNamespace(create=fake_create))),
                          models=["m"], log=lambda *a: None)
        self.assertEqual(result, good)
        self.assertEqual(len(sent), 2)
        self.assertIn("was changed", sent[1])
        status = self.db.execute("SELECT status, attempts FROM gen_job WHERE job_id=?",
                                 (jid,)).fetchone()
        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["attempts"], 2)


class ValidatorTests(unittest.TestCase):
    def test_examiner_questions_must_come_back_verbatim(self):
        payload = {"_part1_questions": ["Do you work or are you a student?"],
                   "_bounds": {"part1": [25, 40]}}
        changed = {"turns": [
            {"role": "examiner", "text": "So, what is your job?"},
            {"role": "candidate", "text": " ".join(["word"] * 30)}]}
        self.assertTrue(any("was changed" in e
                            for e in v.check("P6a1", changed, payload)))

    def test_part2_length_outside_the_band_range_is_rejected(self):
        payload = {"_bounds": {"part2": [250, 300]}}
        self.assertTrue(v.check("P6a2", {"text": " ".join(["w"] * 90)}, payload))
        self.assertFalse(v.check("P6a2", {"text": " ".join(["w"] * 270)}, payload))

    def test_meta_leaks_and_vietnamese_are_caught(self):
        self.assertTrue(v.check("P6b", {"points": ["As an AI, I think so."]}, {}))
        self.assertTrue(v.check("P6b", {"points": ["Tôi rất thích đọc sách."]}, {}))
        self.assertFalse(v.check("P6b", {"points": ["I enjoy reading books."]}, {}))

    def test_a_part3_question_must_pick_up_something_already_said(self):
        """Tiêu chí nghiệm thu UC04, kiểm ngay lúc sinh."""
        payload = {"part3_questions": 2, "_bounds": {"part3": [40, 58]},
                   "_prior_text": "I learned teamwork in a recycling project."}
        answer = " ".join(["word"] * 48)
        grounded = {"turns": [
            {"role": "examiner", "text": "Why do people volunteer?"},
            {"role": "candidate", "text": answer},
            {"role": "examiner", "text": "You mentioned recycling, is it common?"},
            {"role": "candidate", "text": answer}]}
        floating = {"turns": [
            grounded["turns"][0], grounded["turns"][1],
            {"role": "examiner", "text": "Do cities grow quickly?"},
            grounded["turns"][3]]}
        self.assertFalse(v.check("P6a3", grounded, payload))
        self.assertTrue(any("pick up nothing" in e
                            for e in v.check("P6a3", floating, payload)))

    def test_judge_output_must_be_a_band_on_the_real_scale(self):
        good = {"criteria": {"FC": 6, "LR": 6.5, "GRA": 6}, "overall": 6,
                "realism_1_5": 4, "signals": []}
        self.assertFalse(v.check("P10", good, {}))
        self.assertTrue(v.check("P10", {**good, "overall": 11}, {}))
        self.assertTrue(v.check("P10", {**good, "realism_1_5": 9}, {}))

    def test_a_part1_topic_needs_distinct_well_formed_questions(self):
        good = {"topics": [{"name": "Daily routines", "questions": [
            "What time do you usually wake up on weekdays?",
            "How do you normally spend your lunch break?",
            "Do you prefer mornings or evenings for exercise?",
        ]}]}
        payload = {"n_topics": 1, "per_topic": 3, "_avoid": []}
        self.assertEqual(v.check("P6q1", good, payload), [])

        repeated = {"topics": [{"name": "Daily routines", "questions": [
            "What time do you usually wake up on weekdays?",
            "What time do you usually wake up on weekdays?",
            "Do you prefer mornings or evenings for exercise?",
        ]}]}
        self.assertTrue(any("repeats" in e
                            for e in v.check("P6q1", repeated, payload)))

        statement = {"topics": [{"name": "Daily routines", "questions": [
            "Please tell me your morning routine in detail.",
            "How do you normally spend your lunch break?",
            "Do you prefer mornings or evenings for exercise?",
        ]}]}
        self.assertTrue(any("question mark" in e
                            for e in v.check("P6q1", statement, payload)))

    def test_a_topic_already_in_the_bank_is_rejected(self):
        data = {"topics": [{"name": "Daily routines", "questions": [
            "What time do you usually wake up on weekdays?"]}]}
        errors = v.check("P6q1", data,
                         {"n_topics": 1, "per_topic": 1,
                          "_avoid": ["daily routines"]})
        self.assertTrue(any("already in the bank" in e for e in errors))

    def test_a_cue_card_must_keep_the_part2_shape(self):
        good = {"cards": [{
            "title": "A useful habit",
            "text": "Describe a habit you have that makes your day easier.",
            "points": ["what the habit is", "when you started it",
                       "how you keep it up"],
            "explain": "and explain why it matters to you."}]}
        self.assertEqual(v.check("P6q2", good, {"n_cards": 1, "_avoid": []}), [])

        broken = {"cards": [{
            "title": "A useful habit",
            "text": "A habit you have.",
            "points": ["what the habit is", "when you started it"],
            "explain": "Explain why it matters."}]}
        errors = v.check("P6q2", broken, {"n_cards": 1, "_avoid": []})
        self.assertTrue(any("start with 'Describe'" in e for e in errors))
        self.assertTrue(any("exactly 3 points" in e for e in errors))
        self.assertTrue(any("and explain" in e for e in errors))

    def test_boilerplate_does_not_make_two_cards_look_alike(self):
        """Mọi cue card đều mở bằng 'Describe', nên từ đó không tính là trùng."""
        apart = {"cards": [
            {"title": "A concert", "text": "Describe a live concert you went to.",
             "points": ["where it was", "who you went with", "what you heard"],
             "explain": "and explain why you remember it."},
            {"title": "A hard project",
             "text": "Describe a school project that was difficult for you.",
             "points": ["what the goal was", "what went wrong",
                        "how it ended"],
             "explain": "and explain what you learned."}]}
        self.assertEqual(v.check("P6q2", apart, {"n_cards": 2, "_avoid": []}), [])

        same = {"cards": [
            {"title": "A concert", "text": "Describe a live music concert you went to.",
             "points": ["where it was", "who you went with", "what you heard"],
             "explain": "and explain why you remember it."},
            {"title": "A music night",
             "text": "Describe a music concert you went to in your city.",
             "points": ["where it was", "who played", "what you heard"],
             "explain": "and explain how you felt."}]}
        self.assertTrue(any("same subject" in e
                            for e in v.check("P6q2", same,
                                             {"n_cards": 2, "_avoid": []})))

    def test_part3_bank_questions_must_not_be_part1_questions(self):
        payload = {"n_questions": 2}
        good = {"questions": [
            "Why do people keep certain objects for many years?",
            "How has the way families mark special occasions changed?"]}
        self.assertEqual(v.check("P6q3", good, payload), [])

        personal = {"questions": [
            "What is your favourite kind of present to receive?",
            "How has the way families mark special occasions changed?"]}
        self.assertTrue(any("people in general" in e
                            for e in v.check("P6q3", personal, payload)))

    def test_part3_accepts_a_prepositional_opening(self):
        """'In what ways ...' và 'To what extent ...' là dạng Part 3 chuẩn."""
        data = {"questions": [
            "In what ways have digital tools changed how colleagues work together?",
            "To what extent do short breaks help people concentrate at work?"]}
        self.assertEqual(v.check("P6q3", data, {"n_questions": 2}), [])

    def test_spearman_handles_ties(self):
        self.assertAlmostEqual(v.spearman([1, 2, 3], [1, 2, 3]), 1.0)
        self.assertAlmostEqual(v.spearman([1, 2, 3], [3, 2, 1]), -1.0)
        self.assertAlmostEqual(v.spearman([1, 1, 2], [5, 5, 9]), 1.0)


class SpearmanCITests(unittest.TestCase):
    def test_a_clean_trend_gives_a_ci_above_the_threshold(self):
        bands = [4.0, 4.0, 5.0, 5.0, 6.0, 6.0, 7.0, 7.0, 8.0, 8.0]
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        low, high = report.spearman_ci(bands, values, rounds=800)
        self.assertGreater(low, 0.7)
        self.assertLessEqual(high, 1.0)

    def test_noise_gives_a_ci_that_straddles_the_threshold(self):
        """Dấu hiệu 'chưa quyết định được': ngưỡng 0.7 nằm trong khoảng."""
        bands = [4.0, 4.0, 5.0, 5.0, 6.0, 6.0, 7.0, 7.0, 8.0, 8.0]
        values = [1, 9, 2, 10, 4, 6, 8, 3, 7, 5]
        low, high = report.spearman_ci(bands, values, rounds=800)
        self.assertLess(low, 0.7)

    def test_the_ci_is_reproducible_from_its_seed(self):
        bands = [4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5]
        values = [2, 1, 4, 3, 6, 5, 8, 7]
        first = report.spearman_ci(bands, values, rounds=500)
        self.assertEqual(first, report.spearman_ci(bands, values, rounds=500))


class PlanTests(unittest.TestCase):
    def test_the_whole_plan_is_reproducible_from_the_seed(self):
        """Metric P9: chạy lại từ seed phải giống hệt."""
        first, second = planner.build(population_size=30), planner.build(population_size=30)
        self.assertEqual([s["key"] for s in first["benchmark"]],
                         [s["key"] for s in second["benchmark"]])
        self.assertEqual(first["benchmark"][3]["part1_questions"],
                         second["benchmark"][3]["part1_questions"])
        self.assertEqual([l["weaknesses"] for l in first["learners"]],
                         [l["weaknesses"] for l in second["learners"]])

    def test_benchmark_covers_every_band_twice_and_splits_dev_from_test(self):
        state = planner.build(population_size=60)
        bands = [s["intended_band"] for s in state["benchmark"]]
        self.assertEqual(sorted(set(bands)), state["spec"]["bands"])
        for band in state["spec"]["bands"]:
            self.assertEqual(bands.count(band), 2)
        splits = {s["split"] for s in state["benchmark"]}
        self.assertEqual(splits, {"dev", "test"})

    def test_part1_questions_come_from_the_generated_bank(self):
        """Câu hỏi phải khớp từng chữ với bank đã sinh, kể cả q_id."""
        topics = qbank.load()[0]
        lookup = {f"{t['id']}-{n + 1}": q
                  for t in topics for n, q in enumerate(t["questions"])}
        state = planner.build(population_size=30)
        for session in state["benchmark"]:
            self.assertEqual(len(session["part1_questions"]), 8)
            for question in session["part1_questions"]:
                self.assertEqual(lookup[question["q_id"]], question["text"])

    def test_part1_topics_never_clash_with_the_cue_card(self):
        """Hỏi Part 1 về quà rồi Part 2 bắt tả món quà là lỗi ra đề."""
        for session in planner.build(population_size=30)["benchmark"]:
            card = session["cue_card"]
            theme = v.content_words(f"{card['title']} {card['text']}", 4)
            for topic in session["topics"]:
                self.assertFalse(v.content_words(topic["name"], 4) & theme,
                                 f"{session['key']}: {topic['name']}")

    def test_every_question_in_the_plan_is_llm_generated(self):
        """Không câu nào được rơi lại về bank viết tay trong questions.py."""
        from ielts_agent.agents.speaking.questions import QUESTIONS
        handwritten = {q["text"] for q in QUESTIONS.values() if "text" in q}
        state = planner.build(population_size=30)
        for session in state["benchmark"]:
            for question in session["part1_questions"]:
                self.assertNotIn(question["text"], handwritten)
            self.assertNotIn(session["cue_card"]["text"], handwritten)


class QuestionBankTests(unittest.TestCase):
    def test_the_bank_records_enough_provenance_for_r9(self):
        bank = json.loads(qbank.BANK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(bank["schema"], qbank.SCHEMA)
        self.assertEqual(bank["source"], "llm_generated_verified")
        self.assertTrue(bank["license"])
        self.assertTrue(bank["author"])
        self.assertTrue(bank["calls"])
        for call in bank["calls"]:
            for field in ("prompt_id", "prompt_version", "job_id", "model"):
                self.assertTrue(call[field], f"{field} rỗng trong {call}")
            self.assertIn(call["prompt_id"], ("P6q1", "P6q2", "P6q3"))
        produced = [key for call in bank["calls"] for key in call["produced"]]
        stored = ([t["id"] for t in bank["topics"]]
                  + [c["id"] for c in bank["cue_cards"]]
                  # P6q3 sinh theo từng cue card nên id cue card xuất hiện hai lần.
                  + list(bank["part3_bank"]))
        self.assertEqual(sorted(produced), sorted(stored))

    def test_a_missing_bank_is_an_error_not_a_silent_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError):
                qbank.load(Path(folder) / "nope.json")

    def test_ids_are_code_assigned_and_skip_leading_articles(self):
        used = set()
        self.assertEqual(qbank.slug("A challenging project", used),
                         "challenging")
        self.assertEqual(qbank.slug("The quiet place", used), "quiet-place")
        # Tên trùng vẫn phải ra ID khác nhau, nếu không bank ghi đè lẫn nhau.
        self.assertEqual(qbank.slug("A challenging project", used),
                         "challenging-2")

    def test_the_bank_matches_the_size_the_spec_asks_for(self):
        spec = planner.load_spec()["question_bank"]
        topics, cards, sets = qbank.load()
        self.assertEqual(len(topics), spec["topics"])
        self.assertEqual(len(cards), spec["cue_cards"])
        self.assertEqual(len(sets), spec["exam_sets"])
        for topic in topics:
            self.assertEqual(len(topic["questions"]),
                             spec["questions_per_topic"])
        for one in sets:
            self.assertEqual(len(one["part1_topics"]),
                             spec["part1_topics_per_set"])
            self.assertEqual(len(one["part3_fallback_questions"]),
                             spec["part3_fallback_per_set"])

    def test_every_exam_set_is_a_complete_test(self):
        """Một bộ đề phải đủ Part 1 + Part 2 + Part 3 và trỏ vào bank thật."""
        topics, cards, sets = qbank.load()
        topic_ids = {t["id"] for t in topics}
        card_ids = {c["id"] for c in cards}
        for one in sets:
            self.assertTrue(set(one["part1_topics"]) <= topic_ids, one["id"])
            self.assertIn(one["cue_card_id"], card_ids)
            self.assertTrue(one["part3_fallback_questions"], one["id"])

    def test_no_two_exam_sets_reuse_the_same_topic_pair(self):
        sets = qbank.load()[2]
        pairs = [tuple(sorted(one["part1_topics"])) for one in sets]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_an_exam_sets_part1_never_clashes_with_its_cue_card(self):
        topics, cards, sets = qbank.load()
        by_topic = {t["id"]: t for t in topics}
        by_card = {c["id"]: c for c in cards}
        for one in sets:
            card = by_card[one["cue_card_id"]]
            theme = v.content_words(f"{card['title']} {card['text']}", 4)
            for topic_id in one["part1_topics"]:
                self.assertFalse(
                    v.content_words(by_topic[topic_id]["name"], 4) & theme,
                    f"{one['id']}: {topic_id}")

    def test_composing_the_sets_twice_gives_the_same_answer(self):
        spec = planner.load_spec()
        bank = json.loads(qbank.BANK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(qbank.compose(spec, bank), qbank.compose(spec, bank))

    def test_the_selection_rule_is_written_down_next_to_the_data(self):
        """Quy tắc chọn đề phải đọc được từ file, không chỉ nằm trong code."""
        bank = json.loads(qbank.BANK_PATH.read_text(encoding="utf-8"))
        for part in ("part1", "part2", "part3", "per_session"):
            self.assertTrue(bank["selection_rule"][part].strip())

    def test_learner_bands_stay_on_the_ielts_scale(self):
        for learner in planner.build(population_size=80)["learners"]:
            self.assertIn(learner["band_overall"] * 2, range(8, 17))
            self.assertGreaterEqual(learner["target_band"],
                                    learner["band_overall"] + 0.5)

    def test_every_edge_case_group_is_paired_with_a_real_session(self):
        state = planner.build(population_size=30)
        keys = {s["key"] for s in state["benchmark"]}
        groups = {}
        for item in state["edge"]:
            self.assertIn(item["base_key"], keys)
            groups[item["group"]] = groups.get(item["group"], 0) + 1
        self.assertEqual(groups, state["spec"]["edge_cases"])


def fake_session(band=6.0, key="sp-bench-00", part2_words=180):
    turns = []
    for index in range(2):
        turns += [{"role": "examiner", "part": 1, "text": f"Question {index}?"},
                  {"role": "candidate", "part": 1,
                   "text": "I live near the coastal market and walk there daily. "
                           "It is quiet. I enjoy the park."}]
    turns += [{"role": "examiner", "part": 2, "text": "Describe a useful skill."},
              {"role": "candidate", "part": 2,
               "text": " ".join(["cooking vegetables carefully"] * (part2_words // 3))}]
    turns += [{"role": "examiner", "part": 3, "text": "Is cooking taught at school?"},
              {"role": "candidate", "part": 3, "text": "Yes, schools should teach it."},
              {"role": "examiner", "part": 3,
               "text": "You mentioned cooking vegetables, is that common?"},
              {"role": "candidate", "part": 3, "text": "Many families cook vegetables."}]
    return {"key": key, "intended_band": band, "split": "test",
            "learner": "learner-000", "cue_card": "part2-skill",
            "topics": ["home", "leisure"],
            "part1_questions": [{"q_id": "home-1", "text": "Question 0?"}],
            "turns": turns,
            "started_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()}


class AssembleTests(unittest.TestCase):
    def setUp(self):
        self.spec = planner.load_spec()
        self.state = planner.build(population_size=30)
        self.session = self.state["benchmark"][8]
        self.rng = random.Random(7)

    def build(self, variant=None, band=6.0):
        produced = fake_session(band=band, key=self.session["key"])
        produced["started_at"] = self.session["started_at"].isoformat()
        return assemble.build_attempt(self.spec, self.session, produced,
                                      random.Random(7), variant)

    def test_rows_satisfy_the_database_schema(self):
        built = self.build()
        self.assertTrue(built["speaking_turns"])
        self.assertTrue(built["candidate_points"])
        for turn in built["speaking_turns"]:
            self.assertIn(turn["part"], ("part1", "part2", "part3"))
            self.assertTrue(0 <= turn["stt_confidence"] <= 1)
            self.assertGreater(turn["duration_s"], 0)

    def test_turns_never_overlap_on_the_clock(self):
        turns = sorted(self.build()["speaking_turns"], key=lambda t: t["turn_no"])
        for before, after in zip(turns, turns[1:]):
            self.assertGreaterEqual(after["t_start_s"],
                                    before["t_start_s"] + before["duration_s"])

    def test_a_longer_turn_at_a_lower_band_takes_more_time_per_word(self):
        """duration_s suy ra từ số từ, tốc độ nói và thời gian ngắt theo band."""
        slow = assemble.turn_timing(random.Random(1), " ".join(["w"] * 100),
                                    self.spec["band_profiles"][4.0]["speech_rate"],
                                    4.0)
        fast = assemble.turn_timing(random.Random(1), " ".join(["w"] * 100),
                                    self.spec["band_profiles"][8.0]["speech_rate"],
                                    8.0)
        self.assertGreater(slow, fast)

    def test_candidate_points_follow_the_live_agent_rule(self):
        """Agent thật lấy 3 câu đầu mỗi lượt, nên dữ liệu giả lập cũng vậy."""
        built = self.build()
        turn = next(t for t in built["speaking_turns"] if t["part"] == "part1")
        points = [p for p in built["candidate_points"] if p["turn_id"] == turn["id"]]
        self.assertLessEqual(len(points), 3)
        self.assertTrue(all(p["point"] in turn["transcript"] for p in points))

    def test_a_flagged_turn_contributes_no_candidate_point(self):
        built = self.build({"group": "too_short", "key": "e1",
                            "base_key": self.session["key"]})
        self.assertEqual(built["candidate_points"], [])

    def test_injection_lands_in_the_transcript_and_raises_the_flag(self):
        probe = self.spec["injection_probes"][0]
        built = self.build({"group": "injection", "key": "e2", "probe": probe,
                            "base_key": self.session["key"]})
        self.assertTrue(any(probe in t["transcript"]
                            for t in built["speaking_turns"]))
        self.assertTrue(any("injection_detected" in f
                            for f in built["flags"].values()))

    def test_low_confidence_group_deletes_its_audio_after_submission(self):
        built = self.build({"group": "low_stt_confidence", "key": "e3",
                            "base_key": self.session["key"]})
        attempt = built["attempts"][0]
        self.assertEqual(attempt["mode"], "voice")
        self.assertIsNone(attempt["audio_uri"])
        self.assertGreater(attempt["audio_deleted_at"], attempt["submitted_at"])
        for turn in built["speaking_turns"]:
            self.assertLess(turn["stt_confidence"],
                            self.spec["stt"]["low_threshold"])

    def test_a_transcript_only_attempt_stays_in_text_mode(self):
        """Không có audio thì Pronunciation phải là not_assessed (UC-03)."""
        attempt = self.build()["attempts"][0]
        self.assertEqual(attempt["mode"], "text")
        self.assertIsNone(attempt["audio_uri"])
        self.assertIsNone(attempt["audio_deleted_at"])

    def test_the_manifest_keeps_intended_band_out_of_the_database_tables(self):
        """intended_band là tham số thiết kế, không phải điểm chuẩn (1.5.3)."""
        built = self.build()
        row = assemble.manifest_row(self.spec, built, fake_session(), "benchmark")
        self.assertEqual(row["intended_band"], built["intended_band"])
        self.assertTrue(row["is_synthetic"])
        for attempt in built["attempts"]:
            self.assertIsNone(attempt["raw_score"])


class ReportTests(unittest.TestCase):
    def test_qwk_is_one_for_perfect_agreement_and_near_zero_for_noise(self):
        bands = [4.0, 5.0, 6.0, 7.0, 8.0]
        self.assertAlmostEqual(report.qwk(bands, bands), 1.0)
        self.assertLess(report.qwk(bands, list(reversed(bands))), 0)

    def test_monotonic_features_rise_with_the_designed_band(self):
        sessions = [fake_session(band=4.0, key="a", part2_words=60),
                    fake_session(band=6.0, key="b", part2_words=180),
                    fake_session(band=8.0, key="c", part2_words=300)]
        result = report.w2_monotonic(sessions)
        self.assertTrue(result["words"]["pass"])

    def test_identical_sessions_are_caught_as_duplicates(self):
        twin = [fake_session(band=6.0, key="a"), fake_session(band=6.0, key="b")]
        result = report.w4_diversity(twin)
        self.assertEqual(result["pairs_compared"], 1)
        self.assertGreater(result["max_overlap"], 0.03)
        self.assertFalse(result["pass"])

    def test_a_meta_leak_fails_the_report(self):
        leaky = fake_session()
        leaky["turns"][1]["text"] = "As an AI, I would say band 7 is fair."
        self.assertFalse(report.w5_leaks([leaky])["pass"])


if __name__ == "__main__":
    unittest.main()

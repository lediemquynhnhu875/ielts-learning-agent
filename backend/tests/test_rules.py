from copy import deepcopy

import pytest
from ielts_agent.agents.uc04.models import ExerciseDraft, GenerateRequest
from ielts_agent.agents.uc04.rules import contains_phrase, validate_rules, word_count


def request(**updates):
    return GenerateRequest(skill="reading", topic="Can Gio mangroves", target_band=6.0, **updates)


def draft(length=650, count=10):
    text = "The reserve protects coastal forests. Workers plant young trees. "
    text += " ".join(["habitat"] * (length - word_count(text)))
    questions = []
    for index in range(count):
        kind = index % 3
        question = {
            "id": str(index + 1),
            "kind": ["true_false_not_given", "multiple_choice", "sentence_completion"][kind],
            "prompt": "Workers plant ____ in the reserve." if kind == 2 else "What does the reserve protect?",
            "answer": ["TRUE", "A", "young trees"][kind],
            "evidence_span": "Workers plant young trees." if kind == 2 else "The reserve protects coastal forests.",
            "explanation": "The passage gives this information explicitly.",
        }
        if kind == 1:
            question["options"] = {"A": "Coastal forests", "B": "Urban railways", "C": "Large factories"}
        if kind == 2:
            question["word_limit"] = 2
        questions.append(question)
    return ExerciseDraft(title="Coastal habitat", text=text, questions=questions)


def test_valid_reading():
    exercise = draft()
    assert validate_rules(exercise, request(), enforce_requested_count=True).passed


def test_matching_headings_cannot_reuse_one_label_in_the_same_shared_bank():
    exercise = draft()
    exercise.text = "[A]\n" + exercise.text + "\n[B]\nWorkers plant young trees."
    for index, label in [(0, "A"), (1, "B")]:
        q = exercise.questions[index]
        q.kind = "matching_headings"
        q.options = {"i": "Forest protection", "ii": "Research methods", "iii": "New industry"}
        q.paragraph_id = label
        q.answer = "i"
        q.evidence_span = "The reserve protects coastal forests." if label == "A" else "Workers plant young trees."
    report = validate_rules(exercise, request())
    assert "matching_heading_cannot_be_reused" in report.items["2"]


@pytest.mark.parametrize("length,passed", [(599, False), (600, True), (900, True), (901, False)])
def test_reading_length_boundaries(length, passed):
    assert validate_rules(draft(length), request()).passed is passed


@pytest.mark.parametrize("length,passed", [(399, False), (400, True), (700, True), (701, False)])
def test_listening_length_boundaries(length, passed):
    listening = request().model_copy(update={"skill": "listening"})
    assert validate_rules(draft(length), listening).passed is passed


def test_completion_too_long_is_rejected_even_if_verbatim():
    exercise = draft()
    exercise.questions[2].answer = "plant young trees"
    report = validate_rules(exercise, request())
    assert "completion_answer_exceeds_word_limit" in report.items["3"]


def test_completion_requires_exact_case_and_complete_word():
    exercise = draft()
    exercise.questions[2].answer = "Young trees"
    assert "completion_answer_not_verbatim_in_text" in validate_rules(exercise, request()).items["3"]
    assert not contains_phrase("forests", "forest")
    assert contains_phrase("Forests grow here.", "Forests")


def test_completion_limit_must_equal_requested_limit():
    exercise = draft()
    exercise.questions[2].word_limit = 3
    assert "completion_word_limit_must_match_request" in validate_rules(exercise, request()).items["3"]


def test_completion_requires_answer_inside_evidence():
    exercise = draft()
    exercise.questions[2].evidence_span = "The reserve protects coastal forests."
    assert "completion_answer_not_in_evidence" in validate_rules(exercise, request()).items["3"]


@pytest.mark.parametrize("prompt", ["No blank here.", "Workers plant ____ near ____.", "Workers plant _____ here."])
def test_completion_requires_one_blank(prompt):
    exercise = draft()
    exercise.questions[2].prompt = prompt
    assert "completion_requires_one_four_underscore_blank" in validate_rules(exercise, request()).items["3"]


def test_evidence_must_be_an_exact_quote():
    exercise = draft()
    exercise.questions[0].evidence_span = "A fabricated quote."
    assert "evidence_not_in_text" in validate_rules(exercise, request()).items["1"]


@pytest.mark.parametrize("evidence", ["The reserve protects coastal forests.", ""])
def test_not_given_cannot_have_any_evidence(evidence):
    exercise = draft()
    exercise.questions[0].answer = "NOT GIVEN"
    exercise.questions[0].evidence_span = evidence
    assert "not_given_requires_null_evidence" in validate_rules(exercise, request()).items["1"]


def test_not_given_null_is_only_a_structural_check():
    exercise = draft()
    exercise.questions[0].answer = "NOT GIVEN"
    exercise.questions[0].evidence_span = None
    assert validate_rules(exercise, request()).passed


@pytest.mark.parametrize("answer", ["true", "False", "NOT_GIVEN", "YES"])
def test_tfng_requires_canonical_answers(answer):
    exercise = draft()
    exercise.questions[0].answer = answer
    assert "invalid_true_false_not_given_answer" in validate_rules(exercise, request()).items["1"]


def test_option_answer_must_exist_and_options_are_distinct():
    exercise = draft()
    question = exercise.questions[1]
    question.answer = "D"
    question.options["C"] = " coastal forests "
    errors = validate_rules(exercise, request()).items["2"]
    assert "answer_not_in_options" in errors
    assert "options_must_be_distinct" in errors


def test_matching_heading_requires_paragraph_evidence():
    exercise = draft()
    exercise.text = "[A]\n" + exercise.text + "\n[B]\nTransport serves commuters."
    question = exercise.questions[1]
    question.kind = "matching_headings"
    question.paragraph_id = "A"
    assert validate_rules(exercise, request()).passed
    question.evidence_span = "Transport serves commuters."
    assert "matching_evidence_not_in_target_paragraph" in validate_rules(exercise, request()).items["2"]


def test_duplicate_paragraph_labels_are_rejected():
    exercise = draft()
    exercise.text = "[A]\n" + exercise.text + "\n[A]\nTransport serves commuters."
    exercise.questions[1].kind = "matching_headings"
    exercise.questions[1].paragraph_id = "A"
    assert "matching_paragraph_labels_must_be_unique" in validate_rules(exercise, request()).items["2"]


def test_question_count_types_and_ids_are_checked_after_removal():
    exercise = draft()
    exercise.questions = exercise.questions[:7]
    assert any(error.startswith("question_count:") for error in validate_rules(exercise, request()).exercise_errors)
    exercise = draft()
    exercise.questions = [deepcopy(exercise.questions[0]) for _ in range(10)]
    errors = validate_rules(exercise, request()).exercise_errors
    assert "duplicate_question_ids" in errors
    assert "at_least_three_question_types_required" in errors


@pytest.mark.parametrize("count", [8, 13])
def test_valid_count_endpoints(count):
    exercise = draft()
    while len(exercise.questions) < count:
        question = deepcopy(exercise.questions[len(exercise.questions) % 3])
        question.id = str(len(exercise.questions) + 1)
        exercise.questions.append(question)
    exercise.questions = exercise.questions[:count]
    assert validate_rules(exercise, request()).passed
    assert not validate_rules(exercise, request(), enforce_requested_count=True).passed


def test_ielts_word_count_compounds_numbers_and_unicode():
    assert word_count("well-known don't Cần Giờ 1,000 3.5 2026-10-25") == 7


@pytest.mark.parametrize("count", [7, 14])
def test_question_count_outside_bounds_is_rejected(count):
    report = validate_rules(draft(count=count), request())
    assert not report.passed
    assert f"question_count:{count};expected:8-13" in report.exercise_errors


def test_duplicate_id_is_rejected_with_otherwise_valid_types():
    exercise = draft()
    exercise.questions[1].id = exercise.questions[0].id
    report = validate_rules(exercise, request())
    assert not report.passed
    assert report.exercise_errors == ["duplicate_question_ids"]


@pytest.mark.parametrize("evidence", [None, "", "   "])
def test_non_not_given_question_requires_nonblank_evidence(evidence):
    exercise = draft()
    exercise.questions[0].evidence_span = evidence
    report = validate_rules(exercise, request())
    assert not report.passed
    assert "evidence_required" in report.items["1"]


@pytest.mark.parametrize("options,expected", [
    ({"A": "Forests", "B": "Factories"}, "options_require_at_least_three"),
    ({"A": "Forests", "B": "", "C": "Factories"}, "options_must_be_nonblank"),
    ({"A": "Forests", " ": "Railways", "C": "Factories"}, "options_must_be_nonblank"),
])
def test_invalid_choices_report_question_id_and_rule(options, expected):
    exercise = draft()
    exercise.questions[1].options = options
    report = validate_rules(exercise, request())
    assert not report.passed
    assert expected in report.items["2"]


@pytest.mark.parametrize("changes,expected", [
    ({"word_limit": 2}, "word_limit_only_for_completion"),
    ({"paragraph_id": "A"}, "paragraph_id_only_for_matching_headings"),
    ({"options": {"A": "Forests"}}, "options_not_allowed_for_this_type"),
])
def test_fields_are_restricted_to_their_question_type(changes, expected):
    exercise = draft()
    for name, value in changes.items():
        setattr(exercise.questions[0], name, value)
    report = validate_rules(exercise, request())
    assert expected in report.items["1"]
    assert not report.passed


@pytest.mark.parametrize("text,answer", [
    ("A well-known reserve.", "known"),
    ("A well-known reserve.", "well"),
    ("The staff don't travel.", "don"),
    ("The staff don't travel.", "t"),
    ("The staff don’t travel.", "don"),
    ("The staff don’t travel.", "t"),
    ("The result is 3.5 metres.", "3"),
    ("The result is 3.5 metres.", "5"),
    ("They planted 1,000 trees.", "000"),
    ("They planted 1,000 trees.", "1"),
    ("Recorded on 2026-10-25.", "10"),
    ("A well-known reserve protects forests.", "known reserve"),
])
def test_phrase_rejects_fragments_of_single_counted_words(text, answer):
    assert not contains_phrase(text, answer)


@pytest.mark.parametrize("text,answer", [
    ("A well-known reserve.", "well-known"),
    ("The staff don't travel.", "don't"),
    ("The staff don’t travel.", "don’t"),
    ("The result is 3.5 metres.", "3.5"),
    ("They planted 1,000 trees.", "1,000"),
    ("Recorded on 2026-10-25.", "2026-10-25"),
    ("Visit Cần Giờ, then return.", "Cần Giờ"),
    ("Workers plant young trees.", "young trees"),
    ("A well-known reserve; the site is known locally.", "known"),
    ("They planted 1,000 trees in 1 field.", "1"),
    ("Workers said 'young trees'.", "young trees"),
])
def test_phrase_accepts_complete_words_and_later_valid_occurrences(text, answer):
    assert contains_phrase(text, answer)


@pytest.mark.parametrize("text,answer", [
    ("Workers plant young trees.", "Young trees"),
    ("Workers plant young  trees.", "young trees"),
    ("Workers plant young trees.", ""),
])
def test_phrase_still_requires_exact_nonempty_quote(text, answer):
    assert not contains_phrase(text, answer)


@pytest.mark.parametrize("evidence,answer", [
    ("A well-known reserve protects coastal forests.", "known"),
    ("The workers don't travel.", "don"),
    ("The area measures 3.5 hectares.", "3"),
])
def test_completion_rejects_partial_word_in_passage_and_evidence(evidence, answer):
    exercise = draft()
    exercise.text += " " + evidence
    question = exercise.questions[2]
    question.answer = answer
    question.evidence_span = evidence

    report = validate_rules(exercise, request())

    assert not report.passed
    assert "completion_answer_not_verbatim_in_text" in report.items["3"]
    assert "completion_answer_not_in_evidence" in report.items["3"]


def test_completion_rejects_partial_evidence_even_when_passage_has_full_answer():
    exercise = draft()
    exercise.text += " A well-known reserve protects coastal forests. The site is known locally."
    exercise.questions[2].answer = "known"
    exercise.questions[2].evidence_span = "A well-known reserve protects coastal forests."

    report = validate_rules(exercise, request())

    assert not report.passed
    assert "completion_answer_not_in_evidence" in report.items["3"]
    assert "completion_answer_not_verbatim_in_text" not in report.items["3"]


def test_duplicate_ids_identify_each_affected_id_once_and_keep_other_errors():
    exercise = draft()
    exercise.questions[1].id = "1"
    exercise.questions[2].id = "1"
    exercise.questions[4].id = "4"
    exercise.questions[3].answer = "yes"
    original = exercise.model_dump()

    report = validate_rules(exercise, request())

    assert not report.passed
    assert report.exercise_errors == ["duplicate_question_ids"]
    affected = {identifier for identifier, errors in report.items.items()
                if "duplicate_question_id" in errors}
    assert affected == {"1", "4"}
    assert report.items["1"].count("duplicate_question_id") == 1
    assert report.items["4"].count("duplicate_question_id") == 1
    assert "invalid_true_false_not_given_answer" in report.items["4"]
    assert exercise.model_dump() == original
    assert report == validate_rules(exercise, request())


@pytest.mark.parametrize("count", [0, 8, 13])
def test_unique_or_empty_question_ids_have_no_duplicate_details(count):
    report = validate_rules(draft(count=count), request())

    assert "duplicate_question_ids" not in report.exercise_errors
    assert all("duplicate_question_id" not in errors for errors in report.items.values())
    if count == 0:
        assert report.items == {}

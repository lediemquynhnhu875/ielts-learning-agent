"""Fixed-key scoring tests: no model, database or external service."""

from copy import deepcopy

import pytest

from ielts_agent.practice.grading import grade, validate_exercise


@pytest.fixture
def snapshots():
    kinds = ["true_false_not_given", "multiple_choice", "sentence_completion", "matching_headings"]
    exercise = {"id": "item", "skill": "reading", "question_groups": [
        {"question_type": kind, "options": {"A": "Forest protection", "B": "Transport"},
         "response_limits": {"max_words": 2}, "questions": [{"id": f"q{number}", "number": number}]}
        for number, kind in enumerate(kinds, 1)
    ]}
    key = {"item_id": "item", "answers": [
        {"question_id": f"q{number}", "number": number, "answer_key": answer,
         "explanation": "The passage supports this answer.", "evidence_span": "Forest protection."}
        for number, answer in enumerate(["TRUE", "B", "young trees", "A"], 1)
    ]}
    return exercise, key


def test_all_four_types_case_unicode_and_whitespace_normalization(snapshots):
    exercise, key = snapshots
    responses = {"q1": " \ttrue\n", "q2": "ｂ", "q3": " YOUNG\t TREES ", "q4": "a"}
    before = deepcopy((exercise, key, responses))
    result = grade(exercise, key, responses)
    assert result["grading_version"] == "fixed-key-v1"
    assert result["raw_score"] == result["total_questions"] == result["answered_questions"] == 4
    assert result["percentage"] == 100
    assert result["wrong_count"] == result["unanswered_count"] == 0
    assert result["band"] is None and result["band_reason"] == "partial_practice"
    assert [row["reason"] for row in result["questions"]] == ["correct"] * 4
    assert [row["response"] for row in result["questions"]] == list(responses.values())
    assert (exercise, key, responses) == before


def test_missing_and_blank_answers_count_zero_and_preserve_order(snapshots):
    exercise, key = snapshots
    key["answers"].reverse()
    result = grade(exercise, key, {"q1": " \n\t", "q2": "a"})
    assert result["raw_score"] == 0
    assert result["total_questions"] == 4
    assert result["answered_questions"] == result["wrong_count"] == 1
    assert result["unanswered_count"] == 3 and result["percentage"] == 0
    assert [row["question_id"] for row in result["questions"]] == ["q1", "q2", "q3", "q4"]
    assert result["questions"][2]["response"] == ""
    assert result["questions"][1]["reason"] == "incorrect"


@pytest.mark.parametrize("response,reason", [
    ("young trees", "correct"), ("young tree", "incorrect"),
    ("young trees.", "incorrect"), ("plant young trees", "word_limit_exceeded"),
    ("", "unanswered"), ("....", "incorrect"),
])
def test_completion_requires_exact_text_and_obeys_word_limit(snapshots, response, reason):
    exercise, key = snapshots
    result = grade(exercise, key, {"q3": response})
    assert result["questions"][2]["reason"] == reason
    assert result["questions"][2]["correct_answer"] == "young trees"
    assert result["questions"][2]["explanation"] == key["answers"][2]["explanation"]
    assert result["questions"][2]["evidence_span"] == key["answers"][2]["evidence_span"]


@pytest.mark.parametrize("answer,response", [
    ("well-known", "WELL-KNOWN"), ("children's", "CHILDREN'S"),
    ("1,000", "1,000"), ("3.5", "3.5"), ("Cần Giờ", "Cần Giờ"),
])
def test_completion_word_count_matches_existing_hyphen_contraction_number_rules(snapshots, answer, response):
    exercise, key = snapshots
    key["answers"][2]["answer_key"] = answer
    exercise["question_groups"][2]["response_limits"]["max_words"] = 2 if " " in answer else 1
    assert grade(exercise, key, {"q3": response})["questions"][2]["is_correct"]


def test_only_option_labels_and_full_classifications_are_accepted(snapshots):
    exercise, key = snapshots
    key["answers"][0]["answer_key"] = "NOT GIVEN"
    key["answers"][0]["evidence_span"] = None
    wrong = grade(exercise, key, {"q1": "NG", "q2": "Transport", "q4": "Forest protection"})
    assert [row["reason"] for row in wrong["questions"]] == [
        "invalid_classification", "invalid_option", "unanswered", "invalid_option",
    ]
    correct = grade(exercise, key, {"q1": " not\tGIVEN "})
    assert correct["questions"][0]["is_correct"]
    assert correct["questions"][0]["evidence_span"] is None


def test_per_question_option_bank_overrides_group(snapshots):
    exercise, key = snapshots
    exercise["question_groups"][3]["questions"][0]["options"] = {"i": "Protection", "ii": "Research"}
    key["answers"][3]["answer_key"] = "ii"
    assert grade(exercise, key, {"q4": "II"})["questions"][3]["is_correct"]
    assert grade(exercise, key, {"q4": "A"})["questions"][3]["reason"] == "invalid_option"


def test_percentage_rounds_and_wrong_unanswered_totals_are_consistent(snapshots):
    exercise, key = snapshots
    exercise["question_groups"].pop()
    key["answers"].pop()
    result = grade(exercise, key, {"q1": "true", "q2": "a"})
    assert result["percentage"] == 33.33
    assert result["raw_score"] + result["wrong_count"] + result["unanswered_count"] == 3


@pytest.mark.parametrize("change", [
    "foreign_item", "missing_key", "extra_key", "duplicate_key", "duplicate_question",
    "duplicate_number", "mismatched_number", "unsupported_kind", "missing_limit",
    "boolean_limit", "key_exceeds_limit", "invalid_option_key", "invalid_classification_key",
    "colliding_options", "excluded_question", "empty_groups", "empty_questions", "blank_key",
])
def test_malformed_snapshots_are_rejected_before_scoring(snapshots, change):
    exercise, key = snapshots
    if change == "foreign_item":
        key["item_id"] = "foreign"
    elif change == "missing_key":
        key["answers"].pop()
    elif change == "extra_key":
        key["answers"].append({**key["answers"][0], "question_id": "foreign"})
    elif change == "duplicate_key":
        key["answers"].append(deepcopy(key["answers"][0]))
    elif change == "duplicate_question":
        exercise["question_groups"][0]["questions"].append(deepcopy(exercise["question_groups"][0]["questions"][0]))
    elif change == "duplicate_number":
        exercise["question_groups"][1]["questions"][0]["number"] = 1
    elif change == "mismatched_number":
        key["answers"][0]["number"] = 9
    elif change == "unsupported_kind":
        exercise["question_groups"][0]["question_type"] = "choose_two"
    elif change == "missing_limit":
        exercise["question_groups"][2]["response_limits"] = {}
    elif change == "boolean_limit":
        exercise["question_groups"][2]["response_limits"]["max_words"] = True
    elif change == "key_exceeds_limit":
        exercise["question_groups"][2]["response_limits"]["max_words"] = 1
    elif change == "invalid_option_key":
        key["answers"][1]["answer_key"] = "Transport"
    elif change == "invalid_classification_key":
        key["answers"][0]["answer_key"] = "yes"
    elif change == "colliding_options":
        exercise["question_groups"][1]["options"]["a"] = "Another A"
    elif change == "excluded_question":
        exercise["question_groups"][0]["questions"][0]["excluded"] = True
    elif change == "empty_groups":
        exercise["question_groups"] = []
    elif change == "empty_questions":
        exercise["question_groups"][0]["questions"] = []
    else:
        key["answers"][0]["answer_key"] = " \t"
    with pytest.raises(ValueError):
        validate_exercise(exercise, key)
    with pytest.raises(ValueError):
        grade(exercise, key, {})


@pytest.mark.parametrize("responses", [{"foreign": "TRUE"}, {"q1": None}, {"q1": True}, ["TRUE"]])
def test_foreign_or_non_text_responses_are_not_silently_ignored(snapshots, responses):
    with pytest.raises(ValueError):
        grade(*snapshots, responses)

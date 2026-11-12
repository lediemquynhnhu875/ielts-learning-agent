"""l3: Listening-specific rule checks (answer order, proper names must be spelled)."""

import pytest

from ielts_agent.agents.uc04.listening_rules import (
    CONFIRM_THRESHOLD,
    FAMILIAR_NAMES,
    validate_listening_rules,
)
from ielts_agent.agents.uc04.models import ExerciseDraft


def completion(qid, prompt, answer, evidence):
    return {
        "id": qid,
        "kind": "sentence_completion",
        "prompt": prompt,
        "answer": answer,
        "evidence_span": evidence,
        "word_limit": 2,
        "explanation": "The speaker says this.",
    }


def true_false(qid, answer, evidence):
    return {
        "id": qid,
        "kind": "true_false_not_given",
        "prompt": "The office opens early.",
        "answer": answer,
        "evidence_span": evidence,
        "explanation": "The speaker says this.",
    }


def draft(text, *questions):
    return ExerciseDraft(title="Listening", text=text, questions=list(questions))


def check(text, *questions):
    return validate_listening_rules(draft(text, *questions))


# ---------------------------------------------------------------- Rule A: order

ORDER_TEXT = (
    "Good morning. The office opens at nine. Parking is free on weekdays. "
    "The library closes at six. Visitors must sign in at the desk."
)


def test_answers_in_script_order_pass():
    report = check(
        ORDER_TEXT,
        true_false("1", "TRUE", "The office opens at nine."),
        true_false("2", "TRUE", "Parking is free on weekdays."),
        true_false("3", "TRUE", "Visitors must sign in at the desk."),
    )
    assert report.passed
    assert report.items["3"] == []


def test_answer_going_backwards_is_flagged_on_the_later_question():
    report = check(
        ORDER_TEXT,
        true_false("1", "TRUE", "Parking is free on weekdays."),
        true_false("2", "TRUE", "The office opens at nine."),
    )
    assert report.items["1"] == []
    assert report.items["2"] == ["listening_answer_order_violation"]
    assert not report.passed


def test_not_given_question_is_skipped_by_order_check():
    report = check(
        ORDER_TEXT,
        true_false("1", "TRUE", "Parking is free on weekdays."),
        {**true_false("2", "NOT GIVEN", None)},
        true_false("3", "TRUE", "Visitors must sign in at the desk."),
    )
    assert report.passed


def test_order_is_compared_across_the_gap_left_by_a_not_given_question():
    report = check(
        ORDER_TEXT,
        true_false("1", "TRUE", "Parking is free on weekdays."),
        {**true_false("2", "NOT GIVEN", None)},
        true_false("3", "TRUE", "The office opens at nine."),
    )
    assert report.items["3"] == ["listening_answer_order_violation"]


def test_two_questions_with_the_same_evidence_are_not_a_violation():
    report = check(
        ORDER_TEXT,
        true_false("1", "TRUE", "The office opens at nine."),
        true_false("2", "TRUE", "The office opens at nine."),
    )
    assert report.passed


def test_evidence_missing_from_script_is_left_to_the_shared_rules():
    report = check(
        ORDER_TEXT,
        true_false("1", "TRUE", "Parking is free on weekdays."),
        true_false("2", "TRUE", "This sentence is not in the script."),
    )
    assert report.passed


# --------------------------------------------------------- Rule B: names spelled

SPELLED = (
    "Receptionist: Can I have your surname please? "
    "Caller: It's Hart, H-A-R-T. "
    "Receptionist: Thank you. The appointment is on the third floor."
)


def surname_question(answer="Hart", evidence="It's Hart, H-A-R-T."):
    return completion("1", "Surname of the caller: ____", answer, evidence)


def test_surname_that_is_spelled_correctly_passes():
    report = check(SPELLED, surname_question())
    assert report.passed
    assert report.warnings == {}
    assert report.name_checks["1"] == "confirmed"


def test_surname_that_is_not_spelled_fails():
    text = (
        "Receptionist: Can I have your surname please? "
        "Caller: It's Hart. "
        "Receptionist: Thank you. The appointment is on the third floor."
    )
    report = check(text, surname_question(evidence="It's Hart."))
    assert report.items["1"] == ["listening_name_not_spelled"]
    assert report.name_checks["1"] == "confirmed"


def test_spelled_letters_that_do_not_match_the_answer_fail():
    text = SPELLED.replace("H-A-R-T", "H-E-R-T")
    report = check(text, surname_question())
    assert report.items["1"] == ["listening_spelling_mismatch"]


@pytest.mark.parametrize(
    "spelled",
    ["H, A, R, T", "H A R T", "h-a-r-t", "H - A - R - T"],
)
def test_accepted_spelling_formats(spelled):
    text = SPELLED.replace("H-A-R-T", spelled)
    assert check(text, surname_question()).passed


def test_double_letter_notation_is_understood():
    text = (
        "Agent: And your surname? Caller: Campbell, C-A-M-P-B-E-double L. "
        "Agent: Thanks, that is all."
    )
    report = check(
        text,
        completion("1", "Surname: ____", "Campbell", "Campbell, C-A-M-P-B-E-double L."),
    )
    assert report.passed


def test_double_letter_notation_with_wrong_letter_fails():
    text = (
        "Agent: And your surname? Caller: Campbell, C-A-M-P-B-E-double N. "
        "Agent: Thanks, that is all."
    )
    report = check(
        text,
        completion("1", "Surname: ____", "Campbell", "Campbell, C-A-M-P-B-E-double N."),
    )
    assert report.items["1"] == ["listening_spelling_mismatch"]


def test_street_name_must_be_spelled():
    text = (
        "Agent: Which street is it? Caller: Maple Avenue. "
        "Agent: Great, see you there at noon."
    )
    report = check(
        text, completion("1", "The shop is on ____ Avenue.", "Maple", "Maple Avenue.")
    )
    assert report.items["1"] == ["listening_name_not_spelled"]


def test_company_name_spelled_correctly_passes():
    text = (
        "Agent: What company do you work for? Caller: Brightwell, B-R-I-G-H-T-W-E-L-L. "
        "Agent: Thanks."
    )
    report = check(
        text,
        completion("1", "Company: ____", "Brightwell", "Brightwell, B-R-I-G-H-T-W-E-L-L."),
    )
    assert report.passed


def test_spelling_cue_in_script_without_letters_still_fails_a_confirmed_name():
    text = (
        "Agent: What is the company called? How do you spell that? "
        "Caller: Brightwell. Agent: Thanks."
    )
    report = check(
        text,
        completion("1", "Company: ____", "Brightwell", "Brightwell."),
    )
    assert report.items["1"] == ["listening_name_not_spelled"]


# ---------------------------------------------------- familiar names / exemptions


def test_familiar_name_without_spelling_is_not_flagged():
    text = (
        "Agent: Where is the conference? Caller: It is in London next spring. "
        "Agent: Wonderful, thank you."
    )
    report = check(
        text,
        completion("1", "City: ____", "London", "It is in London next spring."),
    )
    assert report.passed
    assert report.name_checks["1"] == "exempt"


def test_common_surname_without_spelling_is_not_flagged():
    text = "Agent: Your surname? Caller: Smith. Agent: Thanks, see you soon."
    report = check(
        text, completion("1", "Surname: ____", "Smith", "Smith.")
    )
    assert report.passed


def test_familiar_name_that_is_spelled_wrongly_still_fails():
    text = (
        "Agent: Which city? Caller: London, L-O-N-D-A-N. Agent: Thanks, see you there."
    )
    report = check(
        text, completion("1", "City: ____", "London", "London, L-O-N-D-A-N.")
    )
    assert report.items["1"] == ["listening_spelling_mismatch"]


def test_familiar_name_spelled_correctly_passes():
    text = (
        "Agent: Which city? Caller: London, L-O-N-D-O-N. Agent: Thanks, see you there."
    )
    assert check(
        text, completion("1", "City: ____", "London", "London, L-O-N-D-O-N.")
    ).passed


@pytest.mark.parametrize("word", ["Monday", "March", "Vietnam", "Hanoi"])
def test_days_months_countries_and_cities_are_familiar(word):
    assert word.casefold() in FAMILIAR_NAMES


# ---------------------------------------------------------------- false positives


def test_common_word_capitalised_at_sentence_start_is_not_a_name():
    text = (
        "Agent: What will you do? Caller: Tomorrow we will visit the museum. "
        "Agent: Sounds lovely."
    )
    report = check(
        text,
        completion(
            "1", "They will visit the ____ tomorrow.", "museum",
            "Tomorrow we will visit the museum.",
        ),
    )
    assert report.passed
    assert report.name_checks["1"] == "not_applicable"


def test_capitalised_first_word_of_the_script_is_not_a_signal():
    text = "Parking is free for visitors on weekdays. The office opens at nine."
    report = check(
        text,
        completion("1", "Visitors get free ____.", "Parking", "Parking is free for visitors"),
    )
    assert report.name_checks["1"] == "uncertain"
    assert report.items["1"] == []
    assert report.warnings["1"] == ["listening_name_unsure"]


def test_lowercase_ordinary_answer_is_never_a_name():
    text = "The tour lasts about two hours and includes lunch. Please bring a hat."
    report = check(
        text,
        completion("1", "Bring a ____.", "hat", "Please bring a hat."),
    )
    assert report.passed
    assert report.name_checks["1"] == "not_applicable"


def test_ordinary_letters_in_the_script_are_not_mistaken_for_spelling():
    text = (
        "Agent: Is that a, b or c? Caller: Option B please. "
        "Agent: The meeting is on Friday."
    )
    report = check(
        text,
        completion("1", "The meeting is on ____.", "Friday", "The meeting is on Friday."),
    )
    assert report.passed


def test_spelling_that_belongs_to_another_answer_is_ignored():
    text = (
        "Agent: Name please. Caller: Hart, H-A-R-T. Agent: And your street? "
        "Caller: Maple Avenue, M-A-P-L-E. Agent: Thanks."
    )
    report = check(
        text,
        completion("1", "Surname: ____", "Hart", "Hart, H-A-R-T."),
        completion("2", "Street: ____ Avenue", "Maple", "Maple Avenue, M-A-P-L-E."),
    )
    assert report.passed


# ------------------------------------------------------------- uncertain -> warning


def test_capitalised_venue_with_no_other_cue_is_only_a_warning():
    # Capitalised mid-sentence AND capitalised in the key is one signal, not two.
    text = (
        "Agent: Where will the workshop be held? Caller: At Harbour Hall, near the pier. "
        "Agent: Thanks."
    )
    report = check(
        text,
        completion("1", "Workshop at the ____.", "Harbour Hall", "At Harbour Hall, near the pier."),
    )
    assert report.name_checks["1"] == "uncertain"
    assert report.passed
    assert report.warnings["1"] == ["listening_name_unsure"]


def test_capitalised_venue_plus_spelling_cue_must_be_spelled():
    text = (
        "Agent: Where will the workshop be held? How do you spell that? "
        "Caller: At Harbour Hall, near the pier. Agent: Thanks."
    )
    report = check(
        text,
        completion("1", "Workshop at the ____.", "Harbour Hall", "At Harbour Hall, near the pier."),
    )
    assert report.name_checks["1"] == "confirmed"
    assert report.items["1"] == ["listening_name_not_spelled"]


def test_familiar_name_with_a_single_signal_gets_no_warning():
    text = "Agent: Where is it? Caller: It is in London next spring. Agent: Thanks."
    report = check(
        text, completion("1", "City: ____", "London", "It is in London next spring.")
    )
    assert report.name_checks["1"] == "exempt"
    assert report.warnings == {}


def test_uncertain_name_gives_warning_without_failing():
    # Only one signal: the answer key is capitalised, but the script has it sentence-initial
    # and the prompt has no cue word.
    text = (
        "Agent: Which room is booked? Caller: Orchid is the one we booked. "
        "Agent: Thanks."
    )
    report = check(
        text,
        completion("1", "Room: ____", "Orchid", "Orchid is the one we booked."),
    )
    assert report.name_checks["1"] == "uncertain"
    assert report.passed
    assert report.warnings["1"] == ["listening_name_unsure"]


def test_uncertain_name_with_wrong_spelling_still_fails():
    text = (
        "Agent: Which room is booked? Caller: Orchid is the one, O-R-C-H-E-D. "
        "Agent: Thanks."
    )
    report = check(
        text,
        completion("1", "Room: ____", "Orchid", "Orchid is the one, O-R-C-H-E-D."),
    )
    assert report.items["1"] == ["listening_spelling_mismatch"]


def test_uncertain_name_with_matching_spelling_has_no_warning():
    text = (
        "Agent: Which room is booked? Caller: Orchid is the one, O-R-C-H-I-D. "
        "Agent: Thanks."
    )
    report = check(
        text,
        completion("1", "Room: ____", "Orchid", "Orchid is the one, O-R-C-H-I-D."),
    )
    assert report.passed
    assert report.warnings == {}


# ------------------------------------------------------------ data-driven config


def test_threshold_and_familiar_names_are_module_level_data():
    assert CONFIRM_THRESHOLD == 2
    assert isinstance(FAMILIAR_NAMES, frozenset)
    assert {"london", "monday", "march", "smith"} <= FAMILIAR_NAMES


def test_non_completion_questions_are_not_name_checked():
    report = check(
        ORDER_TEXT,
        true_false("1", "TRUE", "The office opens at nine."),
    )
    assert report.name_checks == {}


# ------------------------------------------------- merging into the shared report


def test_apply_listening_rules_merges_item_errors_for_listening():
    from ielts_agent.agents.uc04.listening_rules import apply_listening_rules
    from ielts_agent.agents.uc04.models import GenerateRequest
    from ielts_agent.agents.uc04.rules import RuleReport

    text = (
        "Receptionist: Can I have your surname please? Caller: It's Hart. "
        "Receptionist: Thank you."
    )
    exercise = draft(text, surname_question(evidence="It's Hart."))
    report = RuleReport(items={"1": []})
    request = GenerateRequest(skill="listening", topic="Booking a doctor", target_band=6)

    details = apply_listening_rules(exercise, request, report)

    assert report.items["1"] == ["listening_name_not_spelled"]
    assert details["name_checks"] == {"1": "confirmed"}
    assert details["warnings"] == {}


def test_apply_listening_rules_does_nothing_for_reading():
    from ielts_agent.agents.uc04.listening_rules import apply_listening_rules
    from ielts_agent.agents.uc04.models import GenerateRequest
    from ielts_agent.agents.uc04.rules import RuleReport

    exercise = draft(
        "Caller: It's Hart. Receptionist: Thank you.",
        surname_question(evidence="It's Hart."),
    )
    report = RuleReport(items={"1": []})
    request = GenerateRequest(skill="reading", topic="Booking a doctor", target_band=6)

    assert apply_listening_rules(exercise, request, report) is None
    assert report.items == {"1": []}

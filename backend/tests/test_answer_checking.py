"""Fail-closed answer delivery checks using measured turn and recognized word times."""

from ielts_agent.agents.uc04.listening_turns import split_script
from ielts_agent.infrastructure.azure_speech import SpeechTurnTiming
from ielts_agent.infrastructure.azure_stt import DetailedTranscription, RecognizedWord
from ielts_agent.listening.answer_checking import check_answers
from ielts_agent.listening.comparison import words
import pytest


def exercise_and_answers(script, *, key="fifteen", evidence=None, kind="sentence_completion"):
    if evidence is None:
        evidence = split_script(script).turns[0].text
    exercise = {"id": "exercise-1", "skill": "listening", "text": script,
                "question_groups": [{"question_type": kind, "options": {"A": "Seven", "B": "Eleven"},
                                     "questions": [{"id": "question-1", "number": 1, "prompt": "Complete the answer."}]}]}
    answers = {"answers": [{"question_id": "question-1", "number": 1,
                             "answer_key": key, "evidence_span": evidence}]}
    return exercise, answers


def measured_turns(script, *, seconds_per_turn=10):
    return [SpeechTurnTiming(position=turn.position, speaker_id=turn.speaker_id,
                             start_frame=(turn.position - 1) * seconds_per_turn * 24000,
                             end_frame=turn.position * seconds_per_turn * 24000,
                             start_seconds=(turn.position - 1) * seconds_per_turn,
                             end_seconds=turn.position * seconds_per_turn,
                             source_start_char=turn.start_char, source_end_char=turn.end_char)
            for turn in split_script(script).turns]


def recognized_turns(script, actual_turns=None, *, seconds_per_turn=10, complete=True):
    contents = actual_turns or [turn.text for turn in split_script(script).turns]
    recognized = []
    for position, content in enumerate(contents):
        tokens = words(content)
        step = seconds_per_turn / (len(tokens) + 1)
        for index, value in enumerate(tokens):
            start = position * seconds_per_turn + (index + 0.2) * step
            recognized.append(RecognizedWord(text=value, start_seconds=start, end_seconds=start + step * 0.5))
    return DetailedTranscription(text=" ".join(contents), words=recognized, complete=complete)


def check(script, actual_turns=None, **options):
    exercise, answers = exercise_and_answers(script, **options)
    return check_answers(script, exercise, answers, measured_turns(script), recognized_turns(script, actual_turns))


def test_fifteen_and_fifty_cannot_publish_as_equivalent_answers():
    result = check("Man: The fee is fifteen pounds.", ["The fee is fifty pounds."])
    assert not result.delivery_allowed
    assert result.checks[0].status == "failed" and result.checks[0].reason == "answer_evidence_differs"


@pytest.mark.parametrize("reference, transcript, key", [
    ("The fee is fifteen pounds.", "The fee is 15 pounds.", "15"),
    ("The room is 15.", "The room is fifteen.", "fifteen"),
    ("We meet on the third floor.", "We meet on the 3rd floor.", "third"),
], ids=["word-to-digit", "digit-to-word", "ordinal"])
def test_conservative_number_equivalence_can_pass(reference, transcript, key):
    result = check("Man: " + reference, [transcript], key=key)
    assert result.delivery_allowed and result.checks[0].status == "passed"


def test_same_answer_at_wrong_turn_time_is_blocked():
    script = "Man: The fee is fifteen pounds.\nWoman: Thank you."
    exercise, answers = exercise_and_answers(script)
    recognition = recognized_turns(script)
    number = next(word for word in recognition.words if word.text == "fifteen")
    number.start_seconds, number.end_seconds = 11.0, 11.5
    result = check_answers(script, exercise, answers, measured_turns(script), recognition)
    assert not result.delivery_allowed
    assert result.checks[0].status == "failed" and result.checks[0].reason == "answer_outside_expected_turn"


@pytest.mark.parametrize("defect", ["missing", "repeated", "absent-from-script"])
def test_missing_or_ambiguous_evidence_stays_unverifiable(defect):
    script = "Man: Room fifteen.\nWoman: Room fifteen." if defect == "repeated" else "Man: Room fifteen."
    exercise, answers = exercise_and_answers(script, evidence="Room fifteen.")
    if defect == "missing":
        answers["answers"][0]["evidence_span"] = None
    elif defect == "absent-from-script":
        answers["answers"][0]["evidence_span"] = "The fee is fifteen."
    result = check_answers(script, exercise, answers, measured_turns(script), recognized_turns(script))
    assert not result.delivery_allowed and result.checks[0].status == "unverifiable"


def test_spelled_letter_typo_blocks_even_when_surname_was_recognized():
    result = check("Man: Surname Hart, H-A-R-T.", ["Surname Hart, H-A-L-T."], key="Hart")
    assert not result.delivery_allowed and result.checks[0].status == "failed"


@pytest.mark.parametrize("spoken, passed", [("Buses leave at seven.", True), ("Buses leave at eleven.", False)])
def test_multiple_choice_checks_evidence_instead_of_reading_the_letter_a(spoken, passed):
    result = check("Man: Buses leave at seven.", [spoken], key="A", kind="multiple_choice")
    assert result.delivery_allowed is passed
    assert result.checks[0].status == ("passed" if passed else "failed")


@pytest.mark.parametrize("has_evidence", [False, True], ids=["no-evidence", "unrelated-evidence"])
def test_not_given_cannot_be_proven_by_lexical_evidence(has_evidence):
    script = "Man: The library opens at nine."
    exercise, answers = exercise_and_answers(script, key="NOT GIVEN", kind="true_false_not_given")
    if not has_evidence:
        answers["answers"][0]["evidence_span"] = None
    result = check_answers(script, exercise, answers, measured_turns(script), recognized_turns(script))
    assert not result.delivery_allowed and result.checks[0].status == "unverifiable"


def test_inserted_negation_cannot_pass_only_because_key_word_survives():
    result = check("Man: The fee is fifteen pounds.", ["The fee is not fifteen pounds."])
    assert not result.delivery_allowed and result.checks[0].status == "failed"


@pytest.mark.parametrize("script, spoken, key", [
    ("Man: The fee is fifteen pounds.", "The fee is fifteen point five pounds.", "fifteen"),
    ("Man: Your code is 00123.", "Your code is 123.", "00123"),
    ("Man: Surname Hart, h-a-r-t.", "Surname Hart, h-a-l-t.", "Hart"),
    ("Man: Surname Hart, H, A, R, T.", "Surname Hart, H, A, L, T.", "Hart"),
], ids=["changed-decimal", "leading-zero-code", "lowercase-spelling", "comma-spelling"])
def test_answer_context_keeps_decimal_identifier_and_spelling_distinctions(script, spoken, key):
    result = check(script, [spoken], key=key)
    assert not result.delivery_allowed and result.checks[0].status == "failed"


def test_cross_turn_evidence_requires_each_word_in_its_own_turn_window():
    script = "Man: Room fifteen.\nWoman: Meet tomorrow."
    evidence = "Room fifteen.\nWoman: Meet tomorrow."
    exercise, answers = exercise_and_answers(script, key="A", evidence=evidence, kind="multiple_choice")
    recognition = recognized_turns(script)
    recognition.words[0].start_seconds, recognition.words[0].end_seconds = 11.0, 11.5
    result = check_answers(script, exercise, answers, measured_turns(script), recognition)
    assert not result.delivery_allowed and result.checks[0].status == "failed"


@pytest.mark.parametrize("defect", ["partial", "no-words", "no-timings", "missing-key"])
def test_incomplete_recognition_or_metadata_is_not_publishable(defect):
    script = "Man: The fee is fifteen pounds."
    exercise, answers = exercise_and_answers(script)
    recognition, timings = recognized_turns(script), measured_turns(script)
    if defect == "partial":
        recognition.complete = False
    elif defect == "no-words":
        recognition.words = []
    elif defect == "no-timings":
        timings = []
    else:
        answers["answers"] = []
    result = check_answers(script, exercise, answers, timings, recognition)
    assert not result.delivery_allowed and result.checks[0].status == "unverifiable"


def test_empty_question_set_is_not_vacuously_verified():
    script = "Man: The fee is fifteen pounds."
    exercise, answers = exercise_and_answers(script)
    exercise["question_groups"] = []
    result = check_answers(script, exercise, answers, measured_turns(script), recognized_turns(script))
    assert not result.delivery_allowed and not result.checks

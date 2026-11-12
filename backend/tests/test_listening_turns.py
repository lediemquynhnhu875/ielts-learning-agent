"""Script segmentation and HTTP contract checks without cloud or database calls."""

from copy import deepcopy
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from ielts_agent.agents.uc04.listening_turns import MAX_SCRIPT_LENGTH, split_script
from ielts_agent.api.main import create_app
from ielts_agent.core.config import Settings
from .test_api import ApiBank, AUTH, TOKEN
from .test_pipeline import FakeAgents, practice_draft


def assert_source_slices(script, result):
    assert [turn.position for turn in result.turns] == list(range(1, len(result.turns) + 1))
    for turn in result.turns:
        assert script[turn.start_char:turn.end_char] == turn.text
        assert turn.text and turn.text == turn.text.strip()


def test_inline_dialogue_reuses_speakers_and_retains_punctuation():
    script = "Receptionist: Can I have your surname? Caller: It's Hart, H-A-R-T. receptionist: Thank you."
    result = split_script(script)
    assert [(s.id, s.label) for s in result.speakers] == [
        ("speaker_1", "Receptionist"), ("speaker_2", "Caller"),
    ]
    assert [t.speaker_id for t in result.turns] == ["speaker_1", "speaker_2", "speaker_1"]
    assert [t.text for t in result.turns] == ["Can I have your surname?", "It's Hart, H-A-R-T.", "Thank you."]
    assert_source_slices(script, result)


def test_multiline_turns_unicode_and_source_offsets():
    script = "  Narrator: Welcome to Café Study.\r\n\r\n  Student A: Hello!\r\nI need a room.\r\n  Tutor: Room 3.  "
    result = split_script(script)
    assert [t.text for t in result.turns] == ["Welcome to Café Study.", "Hello!\r\nI need a room.", "Room 3."]
    assert_source_slices(script, result)


def test_numbered_roles_normalize_internal_whitespace_and_case():
    script = "Speaker  1: First.\nSPEAKER\t1: Second.\nSpeaker 2: Third."
    result = split_script(script)
    assert [s.label for s in result.speakers] == ["Speaker 1", "Speaker 2"]
    assert [t.speaker_id for t in result.turns] == ["speaker_1", "speaker_1", "speaker_2"]
    assert_source_slices(script, result)


def test_names_established_at_line_starts_can_repeat_inline():
    script = "Alice: Hi.\nJames: Hello. Alice: Thanks."
    result = split_script(script)
    assert [s.label for s in result.speakers] == ["Alice", "James"]
    assert [t.text for t in result.turns] == ["Hi.", "Hello.", "Thanks."]
    assert [t.speaker_id for t in result.turns] == ["speaker_1", "speaker_2", "speaker_1"]
    assert_source_slices(script, result)


@pytest.mark.parametrize("separator", ["\n", " "], ids=["line", "inline"])
def test_known_multiword_names_normalize_case_and_spacing(separator):
    script = f"John Smith: Hello.{separator}JOHN  SMITH: Again.{separator}john\tsmith: Goodbye."
    result = split_script(script)
    assert [(speaker.id, speaker.label) for speaker in result.speakers] == [("speaker_1", "John Smith")]
    assert [turn.text for turn in result.turns] == ["Hello.", "Again.", "Goodbye."]
    assert [turn.speaker_id for turn in result.turns] == ["speaker_1"] * 3
    assert_source_slices(script, result)


def test_compound_known_label_spacing_does_not_reintroduce_nested_role():
    script = "Travel Agent: Welcome. travel\tagent: Your trip is booked."
    result = split_script(script)
    assert [speaker.label for speaker in result.speakers] == ["Travel Agent"]
    assert [turn.text for turn in result.turns] == ["Welcome.", "Your trip is booked."]
    assert [turn.speaker_id for turn in result.turns] == ["speaker_1", "speaker_1"]
    assert_source_slices(script, result)


def test_apostrophe_name_label_preserves_identity_and_speech():
    script = "O'Connor: Hello.\nAlice: Hi. O'CONNOR: Thank you."
    result = split_script(script)
    assert [speaker.label for speaker in result.speakers] == ["O'Connor", "Alice"]
    assert [turn.text for turn in result.turns] == ["Hello.", "Hi.", "Thank you."]
    assert [turn.speaker_id for turn in result.turns] == ["speaker_1", "speaker_2", "speaker_1"]
    assert_source_slices(script, result)


@pytest.mark.parametrize("newline", ["\r", "\r\n"], ids=["cr", "crlf"])
def test_names_after_carriage_return_have_exact_original_offsets(newline):
    script = f"Opening narration.{newline}Alice: Hello.{newline}James: Goodbye."
    result = split_script(script)
    assert [speaker.label for speaker in result.speakers] == ["Narrator", "Alice", "James"]
    assert [turn.text for turn in result.turns] == ["Opening narration.", "Hello.", "Goodbye."]
    assert_source_slices(script, result)


def test_unlabelled_preamble_and_explicit_narrator_share_identity():
    script = "Listen carefully.\nMan: Good morning.\nNarrator: Now answer the questions."
    result = split_script(script)
    assert [s.label for s in result.speakers] == ["Narrator", "Man"]
    assert [t.speaker_id for t in result.turns] == ["speaker_1", "speaker_2", "speaker_1"]
    assert_source_slices(script, result)


@pytest.mark.parametrize("script", [
    "  A single speaker talks.\nAnother paragraph.  ",
    "Note: the meeting starts at 9:30. Visit https://example.org/info.",
    "The reason is: we offer tours.\nWe offer: free maps.",
])
def test_unlabelled_prose_and_non_speaker_colons_are_preserved(script):
    result = split_script(script)
    assert [s.label for s in result.speakers] == ["Narrator"]
    assert [t.text for t in result.turns] == [script.strip()]
    assert_source_slices(script, result)


@pytest.mark.parametrize("script", ["", " \n\t", "\x00Hello", "\ud800", "x" * (MAX_SCRIPT_LENGTH + 1),
                                           "Man:", "Man: \nWoman: Hello.", "Man: Hello. Woman:"],
                         ids=["empty", "blank", "nul", "surrogate", "oversized", "empty-role", "empty-middle", "empty-final"])
def test_invalid_or_empty_turn_scripts_rejected(script):
    with pytest.raises(ValueError):
        split_script(script)


def test_compound_role_labels_do_not_create_overlapping_markers():
    script = "Travel Agent: Your trip is booked.\nTour Guide: Welcome!\nTravel Agent: Enjoy your holiday."
    result = split_script(script)
    assert [s.label for s in result.speakers] == ["Travel Agent", "Tour Guide"]
    assert [t.text for t in result.turns] == ["Your trip is booked.", "Welcome!", "Enjoy your holiday."]
    assert [t.speaker_id for t in result.turns] == ["speaker_1", "speaker_2", "speaker_1"]
    assert_source_slices(script, result)


@pytest.fixture
def listening_api():
    class CountingBank(ApiBank):
        def __init__(self):
            super().__init__()
            self.reads = 0

        def get_item(self, item_id):
            self.reads += 1
            return super().get_item(item_id)

    bank = CountingBank()
    bank.item.update(skill="listening", text="Man: Hello. Woman: Good morning.")
    agents = FakeAgents([practice_draft()])
    with TestClient(create_app(settings=Settings(api_token=TOKEN), bank=bank, agents=agents)) as client:
        yield client, bank, agents


def test_raw_script_and_stored_exercise_apis_match_without_mutations(listening_api):
    client, bank, agents = listening_api
    original = deepcopy(bank.item)
    raw = client.post("/api/listening/turns", json={"script": bank.item["text"]}, headers=AUTH)
    stored = client.get(f"/api/exercises/{bank.item_id}/listening-turns", headers=AUTH)
    assert raw.status_code == stored.status_code == 200
    assert raw.json() == stored.json() == split_script(bank.item["text"]).model_dump()
    assert bank.item == original and not bank.saved
    assert agents.generate_calls == agents.solve_calls == 0
    assert "answer_key" not in raw.text
    assert client.get(f"/api/exercises/{bank.item_id}", headers=AUTH).json() == original


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid"}])
def test_both_routes_authenticate_before_work(listening_api, headers):
    client, bank, agents = listening_api
    assert client.post("/api/listening/turns", json={"script": "Man: Hello."}, headers=headers).status_code == 401
    assert client.get(f"/api/exercises/{bank.item_id}/listening-turns", headers=headers).status_code == 401
    assert bank.reads == 0 and not bank.saved
    assert agents.generate_calls == agents.solve_calls == 0


@pytest.mark.parametrize("payload", [{}, {"script": None}, {"script": 123}, {"script": " "},
                                     {"script": "Hi", "extra": True}, {"script": "Man:"},
                                     {"script": "x" * (MAX_SCRIPT_LENGTH + 1)}])
def test_post_rejects_invalid_body(listening_api, payload):
    client, bank, _ = listening_api
    assert client.post("/api/listening/turns", json=payload, headers=AUTH).status_code == 422
    assert bank.reads == 0 and not bank.saved


@pytest.mark.parametrize("body, expected_status", [
    (b'{"script":"\\ud800"}', 422),
    (b'{"script":"Hello.","\\ud800":"unexpected"}', 422),
    (b'{"script":"\xff"}', 400),
], ids=["surrogate-value", "surrogate-key", "invalid-utf8"])
def test_post_rejects_invalid_unicode_instead_of_server_error(listening_api, body, expected_status):
    client, bank, _ = listening_api
    response = client.post("/api/listening/turns", content=body,
                           headers={**AUTH, "Content-Type": "application/json"})
    assert response.status_code == expected_status
    assert bank.reads == 0 and not bank.saved


def test_get_validates_item_id_and_listening_skill(listening_api):
    client, bank, _ = listening_api
    assert client.get("/api/exercises/not-a-uuid/listening-turns", headers=AUTH).status_code == 422
    assert bank.reads == 0
    assert client.get(f"/api/exercises/{uuid4()}/listening-turns", headers=AUTH).status_code == 404
    bank.item["skill"] = "reading"
    assert client.get(f"/api/exercises/{bank.item_id}/listening-turns", headers=AUTH).status_code == 422
    bank.item.update(skill="listening", text="Man:")
    assert client.get(f"/api/exercises/{bank.item_id}/listening-turns", headers=AUTH).status_code == 422

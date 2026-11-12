"""Listening artifacts are bound to source/key/config and survive repository recreation."""

from copy import deepcopy
import hashlib
from io import BytesIO
from uuid import uuid4
import wave

import psycopg
from psycopg.types.json import Jsonb
import pytest

from ielts_agent.infrastructure.db.bank import Bank
from ielts_agent.infrastructure.db.listening_audio import ListeningAudioStore, config_hash, source_hash
from .test_bank import bank, _draft, _metadata, _request, _trace


def wav_audio():
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x01\x00" * 24)
    return output.getvalue()


def source(bank):
    draft = _draft()
    request = _request().model_copy(update={"skill": "listening"})
    exercise = bank.save_verified(request, draft, _metadata(), _trace(draft))
    return exercise, bank.get_answers(exercise["id"])


def save(store, exercise, key, *, status="verified", voices=None):
    return store.save(exercise["id"], source_hash(exercise, key),
                      config_hash({"voices": voices or ["en-GB-SoniaNeural"], "pipeline": "test-v1"}),
                      wav_audio(), {"turns": [{"start_frame": 0, "end_frame": 24}]},
                      {"delivery_allowed": status == "verified"}, status)


def test_source_digest_is_order_independent_but_binds_private_key_and_text():
    exercise = {"text": "The fee is fifteen pounds.", "id": "exercise"}
    key = {"item_id": "exercise", "answers": [{"answer_key": "fifteen"}]}
    original = source_hash(exercise, key)
    assert original == source_hash(dict(reversed(list(exercise.items()))), deepcopy(key))
    assert original != source_hash({**exercise, "text": "The fee is fifty pounds."}, key)
    changed_key = deepcopy(key)
    changed_key["answers"][0]["answer_key"] = "fifty"
    assert original != source_hash(exercise, changed_key)
    assert len(original) == 64


def test_configuration_digest_changes_for_voice_locale_or_pipeline():
    config = {"voices": ["en-GB-SoniaNeural"], "locale": "en-GB", "pipeline": "v1"}
    original = config_hash(config)
    assert config_hash(dict(reversed(list(config.items())))) == original
    for update in ({"voices": ["en-GB-RyanNeural"]}, {"locale": "en-US"}, {"pipeline": "v2"}):
        assert config_hash({**config, **update}) != original


@pytest.mark.parametrize("update", [
    {"status": "pending"}, {"source_hash": "not-sha256"}, {"config_hash": "A" * 64},
    {"audio": b""}, {"audio": "not-bytes"}, {"manifest": []}, {"verification": None},
], ids=["status", "source", "config", "empty", "type", "manifest", "verification"])
def test_invalid_artifact_rejected_before_database_access(update):
    class NoDatabase:
        def _connection(self):
            raise AssertionError("invalid artifacts must not open a database connection")

    record = {"item_id": str(uuid4()), "source_hash": "a" * 64, "config_hash": "b" * 64,
              "audio": wav_audio(), "manifest": {}, "verification": {}, "status": "blocked"}
    with pytest.raises(ValueError):
        ListeningAudioStore(NoDatabase()).save(**(record | update))


def test_audio_artifact_survives_store_recreation_and_migration_rerun(bank):
    exercise, key = source(bank)
    metadata = save(ListeningAudioStore(bank), exercise, key)
    assert "audio" not in metadata
    bank.initialize()
    artifact = ListeningAudioStore(bank).get(exercise["id"])
    assert artifact["audio"] == wav_audio()
    assert artifact["audio_sha256"] == hashlib.sha256(wav_audio()).hexdigest()
    assert artifact["source_hash"] == source_hash(exercise, key)
    assert artifact["status"] == "verified"
    assert artifact["verification"] == {"delivery_allowed": True}
    assert artifact["audio_id"] == metadata["audio_id"]


def test_new_blocked_outcome_replaces_verified_artifact_for_same_exercise(bank):
    exercise, key = source(bank)
    store = ListeningAudioStore(bank)
    first = save(store, exercise, key)
    blocked = save(store, exercise, key, status="blocked", voices=["en-GB-RyanNeural"])
    artifact = store.get(exercise["id"])
    assert artifact["status"] == "blocked"
    assert artifact["verification"]["delivery_allowed"] is False
    assert artifact["config_hash"] == blocked["config_hash"] != first["config_hash"]
    assert artifact["audio_id"] == first["audio_id"]
    with bank._connection() as connection:
        assert connection.execute("SELECT count(*) AS total FROM listening_audio WHERE item_id=%s",
                                  (exercise["id"],)).fetchone()["total"] == 1


def test_source_and_private_answers_share_one_repeatable_read_snapshot(bank, monkeypatch):
    exercise, key = source(bank)
    get_item = Bank._get_item
    question_id = key["answers"][0]["question_id"]

    def read_then_change_key(connection, item_id):
        snapshot = get_item(connection, item_id)
        with psycopg.connect(bank.database_url) as writer:
            writer.execute("UPDATE question SET answer_key=%s WHERE id=%s",
                           (Jsonb({"answer": "FALSE", "explanation": "Changed after snapshot."}), question_id))
        return snapshot

    monkeypatch.setattr(Bank, "_get_item", staticmethod(read_then_change_key))
    loaded_exercise, loaded_key = ListeningAudioStore(bank).load_source(exercise["id"])
    assert loaded_exercise == exercise
    assert loaded_key == key
    assert bank.get_answers(exercise["id"])["answers"][0]["answer_key"] == "FALSE"


def test_nonlistening_or_invalidated_item_has_no_source(bank):
    draft = _draft()
    reading = bank.save_verified(_request(), draft, _metadata(), _trace(draft))
    store = ListeningAudioStore(bank)
    assert store.load_source(reading["id"]) is None
    assert store.load_source(str(uuid4())) is None
    with bank._connection() as connection:
        connection.execute("UPDATE content_item SET skill='Listening',status='rejected' WHERE item_id=%s", (reading["id"],))
    assert store.load_source(reading["id"]) is None


def test_source_changes_invalidate_the_artifact_binding_without_changing_audio(bank):
    exercise, key = source(bank)
    store = ListeningAudioStore(bank)
    save(store, exercise, key)
    with bank._connection() as connection:
        connection.execute("UPDATE question SET answer_key=%s WHERE id=%s",
                           (Jsonb({"answer": "FALSE", "explanation": "Revised fixed key."}), key["answers"][0]["question_id"]))
    current_exercise, current_key = store.load_source(exercise["id"])
    artifact = store.get(exercise["id"])
    assert artifact["source_hash"] != source_hash(current_exercise, current_key)
    assert artifact["audio"] == wav_audio()

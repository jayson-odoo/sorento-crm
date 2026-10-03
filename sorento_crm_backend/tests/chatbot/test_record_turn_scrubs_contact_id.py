"""PII-SCRUB AC-14: `chatbot_record_turn._scrub_contact` must not write the real
Respond.io contact id anywhere into the scrubbed contact. Ids are synthetic and
built at runtime."""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "chatbot_record_turn_ac14", _BACKEND / "scripts" / "chatbot_record_turn.py"
)
assert _spec is not None and _spec.loader is not None
recorder = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("chatbot_record_turn_ac14", recorder)
_spec.loader.exec_module(recorder)

_GUARD_SPEC = importlib.util.spec_from_file_location(
    "pii_guard_ac14", _BACKEND.parent / "scripts" / "pii_guard.py"
)
assert _GUARD_SPEC is not None and _GUARD_SPEC.loader is not None
guard = importlib.util.module_from_spec(_GUARD_SPEC)
sys.modules.setdefault("pii_guard_ac14", guard)
_GUARD_SPEC.loader.exec_module(guard)


def _real_id(rng: random.Random) -> str:
    return "".join(rng.choice("13579") for _ in range(9))


def _scrubbed(real_id: str) -> dict:
    contact = {
        "id": int(real_id),
        "firstName": "Real",
        "lastName": "Person",
        "email": "someone@example.org",
        "phone": "+60" + real_id,
    }
    recorder._scrub_contact(contact)
    return contact


def test_no_real_contact_id_survives_in_the_scrubbed_contact():
    rng = random.Random(21)
    real = _real_id(rng)
    contact = _scrubbed(real)
    assert real not in json.dumps(contact)
    assert real not in str(contact["id"])


def test_fake_id_is_stable_and_distinct_per_real_id():
    rng = random.Random(22)
    a, b = _real_id(rng), _real_id(rng)
    assert a != b
    assert _scrubbed(a) == _scrubbed(a)
    assert _scrubbed(a)["id"] != _scrubbed(b)["id"]
    assert _scrubbed(a)["phone"] != _scrubbed(b)["phone"]


def test_fields_derive_from_one_fake_id_and_pass_the_guard():
    rng = random.Random(23)
    contact = _scrubbed(_real_id(rng))
    fake_id = str(contact["id"])
    assert fake_id in contact["firstName"]
    assert fake_id in contact["email"]
    assert guard.is_fake_phone(contact["phone"])
    assert guard.scan_text(json.dumps(contact)) == []

"""PII-SCRUB - public-repo personal-data guard.

The repo is public. `scripts/pii_guard.py` fails CI when a tracked file holds a
Malaysian mobile number or a lorry plate that is not one of the agreed fake
values, or when a tracked path is a raw capture (`.playwright-mcp/`, `*.har`,
`*.rdb`) that carries prod-copy data. These tests pin the detector rules and
then run it over the whole checkout, so the suite is red while real data is
tracked.

Detection inputs are built at runtime from random digits, so this file never
holds a phone-shaped literal of its own.

The script lives at repo-root `scripts/pii_guard.py`; it is loaded by path so
these tests run from the backend test suite.
"""
from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "pii_guard.py"
_MOD_NAME = "pii_guard_test"


def _load_module():
    spec = importlib.util.spec_from_file_location(_MOD_NAME, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MOD_NAME] = module
    spec.loader.exec_module(module)
    return module


def _random_subscriber(rng: random.Random) -> str:
    # 7 digits with no zero run and no ascending/descending run, i.e. a value
    # the allowlist must NOT treat as fake.
    while True:
        digits = "".join(rng.choice("123456789") for _ in range(7))
        if not _load_module().is_fake_phone("6012" + digits):
            return digits


def _kinds(findings):
    return sorted({f.kind for f in findings})


def test_real_looking_mobile_is_flagged_in_every_format():
    mod = _load_module()
    rng = random.Random(1)
    sub = _random_subscriber(rng)
    for text in (
        f'"wa_id": "6017{sub}"',
        f"call +6017{sub} now",
        f"call +60 17-{sub[:3]} {sub[3:]} now",
        f"call 017-{sub[:3]} {sub[3:]} now",
        f"call 017{sub} now",
    ):
        assert _kinds(mod.scan_text(text)) == ["phone"], text


def test_fake_phones_pass():
    mod = _load_module()
    for text in (
        "+60100000001",
        "60100000519",
        "0100000001",
        "+60123456789",
        "012-345 6789",
        "+60 12-345 6789",
    ):
        assert mod.scan_text(text) == [], text


def test_long_digit_runs_are_not_phones():
    mod = _load_module()
    rng = random.Random(2)
    sub = _random_subscriber(rng)
    # Embedded in a longer number (timestamps, ids) is not a phone.
    assert mod.scan_text(f"id 99017{sub}11") == []
    assert mod.scan_text(f"ts 17{sub}123") == []


def test_plate_in_lorry_plate_context_is_flagged():
    mod = _load_module()
    for text in (
        "*Driver:* DRIVER A\\n*Lorry Plate:* VQB 4821\\n",
        '{"label": "Lorry Plate", "value": "WXY4821"}',
        '"lorry_plate": "JRT 7012 A"',
    ):
        assert _kinds(mod.scan_text(text)) == ["plate"], text


def test_fake_plate_passes():
    mod = _load_module()
    for text in (
        "*Lorry Plate:* PLATE-1\\n",
        '{"label": "Lorry Plate", "value": "PLATE-12"}',
        '"lorry_plate": null',
        '"lorry_plate": ""',
    ):
        assert mod.scan_text(text) == [], text


def test_raw_capture_paths_are_forbidden():
    mod = _load_module()
    assert mod.forbidden_path(".playwright-mcp/page-1.yml")
    assert mod.forbidden_path("documentation/plans/x/evidence/step.har")
    assert mod.forbidden_path("dump.rdb")
    assert not mod.forbidden_path("documentation/plans/x/PLAN-y.md")


def test_findings_never_echo_the_value():
    mod = _load_module()
    rng = random.Random(3)
    sub = _random_subscriber(rng)
    [finding] = mod.scan_text(f"x +6019{sub} y")
    assert sub not in mod.format_finding("a.md", finding)


def test_tracked_tree_is_clean():
    mod = _load_module()
    problems = mod.scan_repo(_REPO_ROOT)
    report = "\n".join(mod.format_finding(path, f) for path, f in problems[:50])
    assert problems == [], f"{len(problems)} PII findings:\n{report}"

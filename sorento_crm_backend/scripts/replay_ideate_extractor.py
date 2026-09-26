"""Replay the #1277 owner transcript through the ideation extractor (live LLM).

Prints what the extractor emits for each user turn of the owner's 26 Sep 2026 console
test, and the captured draft after each turn, so the Problem statement the recap would
show can be compared before and after an ``ideate_extractor`` prompt change.

It runs whatever code and prompt the checkout holds: the prompt is the
``ideate_extractor`` fallback text in ``app.services.ai_prompt_registry`` (the text the
``ideation_reply_fmt_prompts`` migration publishes), never the DB row. For the BEFORE
run, check out the previous commit in a worktree and run the same command there.

No database, no shared service: the provider config comes from the environment and the
shared service's field merge is simulated as "latest value per key wins", which is what
the intake does with ``fields`` (the extractor sends the FULL merged value).

    OPENAI_API_KEY=sk-... venv/bin/python scripts/replay_ideate_extractor.py
    # optional: IDEATE_REPLAY_PROVIDER=anthropic IDEATE_REPLAY_API_KEY=... IDEATE_REPLAY_MODEL=...
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import ai_prompt_registry, ideation_extractor  # noqa: E402

# The owner's turns, verbatim from #1277. "both" answered the media menu, so it never
# reached the extractor on the live turn either (media_selection path); it is kept here
# only to show the extractor leaves the draft alone when handed it.
TURNS = [
    "i ahve an idea, i want sale sorder report to track KKPI",
    "both",
    "i think the problem is, the sales team is not performing",
    "i guess, it will boost sales?",
    "will be sales manager",
    "yea",
]

FIELD_LABELS = {
    "problem": "Problem statement",
    "proposed_solution": "Proposed solution",
    "impact": "Impact",
    "department": "Department",
}


def _config() -> SimpleNamespace:
    provider = os.environ.get("IDEATE_REPLAY_PROVIDER", "openai")
    key = os.environ.get("IDEATE_REPLAY_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("Set OPENAI_API_KEY (or IDEATE_REPLAY_API_KEY) to replay against a live model.")
    model = os.environ.get("IDEATE_REPLAY_MODEL", "gpt-4o-mini")
    return SimpleNamespace(provider=provider, api_key_ciphertext=key, model=model)


def main() -> None:
    config = _config()
    prompt = ai_prompt_registry.PROMPT_KEYS["ideate_extractor"].fallback()
    captured: dict[str, str] = {}
    title = ""
    status = None
    with patch.object(
        ideation_extractor, "AIAssistantConfigService", lambda _db: SimpleNamespace(get=lambda: config)
    ), patch.object(ideation_extractor.ai_prompt_registry, "render", lambda _db, _name: (prompt, None)):
        for turn in TURNS:
            next_field = None
            if captured:
                next_field = next(
                    (k for k in ("proposed_solution", "impact") if k not in captured), None
                )
            out = ideation_extractor.extract_ideate_turn(
                None,
                message_text=turn,
                status=status,
                missing=[],
                next_field=next_field,
                field_labels=FIELD_LABELS,
                captured=dict(captured),
                prior_title=title or None,
            )
            captured.update({k: v for k, v in out.fields.items() if v})
            title = out.title or title
            status = "review" if "impact" in captured else "collecting"
            print(f"> {turn}")
            print(f"  fields: {out.fields}")
            print(f"  title: {title!r}  review_action: {out.review_action}")
            for key in ("problem", "proposed_solution", "impact", "department"):
                if key in captured:
                    print(f"  {key}: {captured[key]}")
            print()


if __name__ == "__main__":
    main()

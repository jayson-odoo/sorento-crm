"""The exact replies CHATBOT-FAIL-TRIAGE batch 1 promises (UAC AC-1, AC-2), in one place.

Not a test module (no `test_` prefix): the new red file and the existing tests whose old
assertions moved onto these texts import from here, so the wording is stated once.
"""
from __future__ import annotations

H_AI = "I could not read your message just now because our AI service did not answer. Please send it again."
H_ERROR = "I hit an error while answering this and could not finish it. Please send it again."
H_QUEUE = "I was still answering your previous message, so I could not take this one. Please send it again."
H_OFFER = "What can I check for you? Stock, incoming, delivery orders, promotions or product details."
H_ESC = "I could not pass this to the {team} team just now. Please contact them directly."

AC2_NONE_FOUND = "No current {label} found for {subject}."
AC2_ASK_SUBJECT = "Which customer or salesperson should I check the {label} for?"
AC2_ASK_PRODUCT = "Which product do you want the {label} for? Send me the code."
AC2_COULD_NOT_FETCH = "I could not fetch {label} just now, please try again."
AC2_NOT_PERMITTED = "That report is not available on your account."

#: Every new EN sentence the batch adds, for the AC-4 catalog coverage test.
NEW_EN_TEXTS = (H_AI, H_ERROR, H_QUEUE, H_ESC, AC2_NONE_FOUND, AC2_ASK_SUBJECT, AC2_ASK_PRODUCT, AC2_NOT_PERMITTED)

#: Substrings of the two banned texts in every language (owner rule, 30 Oct 2026).
BANNED_FRAGMENTS = (
    "busy right now",  # RATE_LIMITED_REPLY
    "ran into a problem understanding",  # CHATBOT_TURN_ERROR_REPLY EN
    "menghadapi masalah memahami",  # MS
    "暂时无法理解",  # ZH
)


def assert_no_banned_text(text: str | None) -> None:
    assert isinstance(text, str) and text.strip(), "the contact was left with no reply"
    low = text.lower()
    for fragment in BANNED_FRAGMENTS:
        assert fragment.lower() not in low, f"banned generic failure text {fragment!r} in {text!r}"


# Review round 1 (R1-R7): the shapes the follow-up tests share.
PORTAL_COULD_NOT_FIND = "could not find portal link"

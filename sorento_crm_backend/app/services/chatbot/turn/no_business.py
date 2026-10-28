# GREETING-NOT-STOCK (prod turns 2bb06537 / 699ce720, Oct 2026): a bare "Hi" from a contact
# whose profile remembers a usual product came back as a stock answer for that product. The
# remembered product reaches the parser as context, and the parser (Gemini flash-lite for a
# staff-tagged contact) sometimes reads a greeting as a stock ask for it. Not every time:
# another "Hi" two minutes later got a hello.
#
# The rule (owner, 28 Oct 2026): a message with no business content (a greeting, thanks, ok,
# an emoji) never becomes a business ask from context alone. Remembered products may only
# fill a slot of a message that IS an ask ("eta?" still resolves to the usual product).
#
# A deterministic guard after the parse, not a prompt edit: a prompt can only make the slip
# rarer, and the slip is already rare. The test is on the WORDS, deliberately narrow: every
# word of the message is on a short list of greetings, thanks, acknowledgements and address
# terms, or the message is emoji and punctuation only. Anything else (a code, a number, a
# domain word, "eta") is left to the parser untouched.
from __future__ import annotations

import re
from typing import Any

from app.services.chatbot.turn.apply import _CASUAL_TYPES, _IDLE_CHAT_DISQUALIFIERS

#: Every word a no-business message may be made of. English, Malay and Chinese, the
#: languages the contacts write in; a word missing here only means the guard stays out of
#: the way (the parser decides, as before).
_NO_BUSINESS_WORDS: frozenset[str] = frozenset(
    {
        # greetings
        "hi", "hello", "helo", "hey", "heya", "hai", "yo", "morning", "afternoon", "evening",
        "night", "good", "gd", "gm", "selamat", "pagi", "petang", "malam", "salam",
        "assalamualaikum", "waalaikumsalam", "你好", "您好", "早", "早安", "早上好", "晚安", "哈喽",
        # thanks
        "thanks", "thank", "thankyou", "thx", "tq", "tqvm", "ty", "tks", "terima", "kasih",
        "谢谢", "多谢", "感谢", "you", "u", "very", "much", "a", "lot",
        # acknowledgements
        "ok", "okay", "okie", "okey", "k", "kk", "noted", "alright", "cool", "nice", "great",
        "got", "it", "好", "好的", "收到",
        # farewells
        "bye", "goodbye", "cya",
        # address terms and fillers
        "boss", "bos", "bro", "sis", "sir", "madam", "dear", "there", "everyone", "team",
        "lah", "la", "ya", "yeah", "ah", "oh", "and", "老板",
    }
)

_WORD = re.compile(r"[^\W_]+")
_RUN = re.compile(r"(.)\1+")


def _squeeze(word: str) -> str:
    """"hiii" / "okkk" / "helloooo" read as their plain word: every run of one letter is one."""
    return _RUN.sub(r"\1", word)


_SQUEEZED_WORDS: frozenset[str] = frozenset(_squeeze(w) for w in _NO_BUSINESS_WORDS)


def is_no_business(text: str) -> bool:
    """True when the message carries no business content at all: every word is a greeting,
    thanks, acknowledgement or address term, or there are no words (emoji and punctuation
    only). An empty message is NOT one (a photo with no caption is a business turn)."""
    text = str(text or "").strip()
    if not text:
        return False
    for word in _WORD.findall(text.casefold()):
        if word not in _NO_BUSINESS_WORDS and _squeeze(word) not in _SQUEEZED_WORDS:
            return False
    return True


def without_context_ask(
    verdict: dict[str, Any], *, text: str, quoted: bool, media: bool, open_question: Any
) -> tuple[dict[str, Any], bool]:
    """The verdict with every business signal dropped when the message itself has none, and
    whether anything was dropped.

    Only a turn with nothing on the table: an open question ("ok" to a stock offer, "thanks"
    to a pick) is the LIVE conversation's to answer, and a quoted reply or a photo brings its
    own subject. Otherwise a no-business message is filed as casual with every key `apply`
    reads as "this message asked something" (`_IDLE_CHAT_DISQUALIFIERS`) cleared, so it plans
    no fetch and the carried focus is left as it was."""
    if open_question is not None or quoted or media or not is_no_business(text):
        return verdict, False
    asked = verdict.get("message_type") not in _CASUAL_TYPES or any(
        verdict.get(key) for key in _IDLE_CHAT_DISQUALIFIERS
    )
    if not asked:
        return verdict, False
    cleared = dict(verdict)
    cleared["message_type"] = "casual"
    for key in _IDLE_CHAT_DISQUALIFIERS:
        if key not in cleared:
            continue
        if key == "continuation":
            cleared[key] = False
        elif isinstance(cleared[key], list):
            cleared[key] = []
        else:
            cleared[key] = None
    return cleared, True

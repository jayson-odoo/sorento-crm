# UAC - Chatbot: one open-question object for every question the bot asks (#1293)

Plan: `PLAN-chatbot-open-question-object.md`

- **AC-OQ01** Every open question the bot carries is stated to the parser as one `Open
  question: {...}` JSON line: a pick list is `pick_one`, a yes/no or one-option did-you-mean is
  `confirm`, a brand roster is `choose_brand`, a question with no options is `free`, the stock
  quantities question is `quantities` (status asked or answered). The object never carries a
  code the resolver did not recognise.
- **AC-OQ02** The parser's `open_question_answer` declares `mode` pick / yes / no / fill / all /
  done / cancel / null, `items` [{position, code, qty}] and `qty_for_all`, strict-schema safe;
  a recorded emission without it still passes (`TOLERATED_ABSENT`).
- **AC-OQ03** "the first one, I need 2" under "Couldn't find STWC2867. Did you mean: 1.
  SRTWC286-SH 2. SRTWC286-SH-P" answers SRTWC286-SH x 2 in that one turn, whether the parser
  declares it (the object) or only emits a position and a quantity (the fallback).
- **AC-OQ04** A quantity with no pick under a did-you-mean asks "Which one do you need 2 of?"
  over the numbered options; no reply after the did-you-mean repeats the unrecognised code.
- **AC-OQ05** Picks by position, by code, by ordinal word, several at once ("both", "1 and 3",
  "all of them"), with a quantity each or one for all; "none of them" / "no" refers the dealer
  to their salesman; a yes over a one-option did-you-mean picks it, with its quantity.
- **AC-OQ06** Mode null leaves the open question unanswered and the message runs as its own ask.
  An object that places on no option is not applied; the shape rules decide.
- **AC-OQ07** Ordinals and numbers in English, Malay and Chinese are taught in the parser
  prompt; no code in `turn/` reads a message word.
- **AC-OQ08** The owner's 26 Sep console sessions (07:18Z, 08:18Z, 10:11Z, 14:06Z) replay
  through `engine.run_turn` with the parser stubbed as it should answer, each reply as ruled.
- **AC-OQ09** Ten natural phrasings per question kind pass.
- **AC-OQ10** A migration publishes the new parser prompt as the next `chatbot_semantic_parser`
  version, label unmoved; one alembic head.

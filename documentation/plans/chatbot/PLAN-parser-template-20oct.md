# PLAN: PARSER-TEMPLATE (F1, one consolidated parser prompt)

Status: Plan, awaiting crew on ask a29454970 (where it lives, CHAT-STATE hand-over, #1755 prompt freeze). Owner:
CHAT-CODE-LOOKUP (crew architecture review, 20 Oct, crew/state/reports/CHAT-ARCH-REVIEW-20oct.md M1 + F1 + section 3).
Track: L, LEAD pattern. Owner 20 Oct: keep the bars, fix at the architecture layer.

## Problem (M1)

The parser prompt is a stack of absolute rules with no precedence. Each lane appended an "overrides" section:
CLOSED LISTS (#1755, 6.2 KB), CODE LOOKUP (#1761, 3.2 KB) and STATE (#1772, 6.1 KB, which aliases base sections).
v178 is 137 KB (v63 141 KB); with STATE about 143 KB. "How this message relates to what is held" lives in 7+ base
sections plus STATE and CODE LOOKUP, over 4 schema channels (open_question_answer.mode, state_changes, entity_op,
reference_positions). One decision has opposite rules: #1761 "a count beside a code is a stock ask whatever the previous
domain" vs #1772 r2-D "a message naming only another item asks the last answer's fact"; the same decision is also a regex
in engine.py `_as_a_stock_ask_by_its_own_words`.

## Design

- One template module (rule-id blocks) and one publisher; versions published unlabelled; the gate markers stay so the
  code paths that read them switch on unchanged.
- An ordered procedure: P1 the relation of this message to the State (state_changes is the only continuation channel
  under the state gate); P2 the entities named in THIS message, picked from the candidate block or none; P3 domain and
  the remaining fields.
- Rule ids; an exception only as "see R-x"; one rule per decision.
- R-DOM-QTY (replaces both count rules and the regex): a stated quantity continues the last answer's domain when that
  domain takes a quantity (stock, incoming, order); otherwise the domain is stock. Derived from the schema, no word list.
- Word lists become meaning rules (the "when deliver" list becomes: asking when goods reach a customer is an
  outstanding order status ask).

## Deletes

- The three appended sections (folded into the base as edits).
- The 7 overlapping continuation sections, and the continuation semantics of open_question_answer / entity_op /
  reference_positions under the state gate.
- Base ATTACHMENT TYPE EXTRACTION canonical rule and the cert-scheme EXCEPTION; the REQUESTED ATTRIBUTES closed
  vocabulary; CODE LOOKUP override paragraphs.
- The R2-5 when-deliver insertion and its publisher anchor code; `_as_a_stock_ask_by_its_own_words` under the gate.

## Gate

- $0 lint (pytest): every rule has an id; fails on two absolute rules over one schema field without a "see R-x" link,
  on any overrides / alias section, on a word list longer than 8 items.
- Size: <= 90 KB (stretch 75 KB).
- Parser gold N=3 on fresh conflict-pair shapes, old (v178 + STATE) vs new; when-deliver gold must stay >= 31/42.
- L1 replay; TRAIN x1 paired (code, follow-ups, attachment, spec) on a combined build. Spend <= USD 4.

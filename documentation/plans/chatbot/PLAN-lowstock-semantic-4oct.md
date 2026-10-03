# PLAN: low stock asks fully semantic, hard-coded rules removed (LOWSTOCK-SEMANTIC)

Status: planning (4 Oct 2026). Track: M (LEAD pattern), no migration of schema; one new
unlabelled parser prompt version.
Card: `lowstock-semantic-behaviour-card.md` (to follow).

## Owner report (4 Oct 2026, 03:00, gist)

"I thought I said we need to be semantic and flexible... remove the rules entirely, this is
hard coded, I don't want."

#1445 reads the low stock ask with rules in `low_stock_ask.py`: a product word without digits
is read as a category, "by supplier" / "by category" regexes, and the supplier is whatever
leftover words match the supplier master. Goal: understanding comes ONLY from the semantic
parser; code only resolves the parser's hints against master data, and asks when a needed
field is missing or ambiguous.

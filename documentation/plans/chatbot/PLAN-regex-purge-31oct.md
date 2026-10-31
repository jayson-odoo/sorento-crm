# PLAN: REGEX-PURGE (chatbot understanding comes from the parser only)

Status: Parked by the owner, 31 Oct 2026 ("it is fine, don't purge first"). Step 1 done, card filed (`regex-purge-behaviour-card.md`); Q1-Q5 unanswered, no code written, no PR. Track: M, LEAD pattern. On pick-up: re-verify the card's file:line against current main first (audit was at b440c715e5, before #2030).

## Rule

Owner, 4 Oct, 28 Oct, 31 Oct: chatbot UNDERSTANDING comes from the semantic parser only. No regex
phrase matching, no keyword or word lists, no post-parse word guards. Code only resolves parser
hints against master data, and asks a short question when unclear. Never add a new word or regex
rule while removing an old one.

## Step 1 (no code)

Audit `app/services/chatbot/**` and `app/services/product_code_family.py` for every regex, word list
or keyword check that reads message text or parser free text (`user_goal` etc.). File one
`crew report --ask` card: site, what it does, what parser field already carries the meaning (or what
field would need adding), keep/replace/remove, eval risk. At most 5 questions with recommendations.

## Step 2 (after the owner picks the list)

Replace with parser fields, red-first. Parser gold + hidden gate via crew (crew runs hidden), live
console pass, reviewer. UAC goes alongside this file once the list is decided.

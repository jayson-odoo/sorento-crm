# PLAN-chat-release-1021c: release PR for the owner-tested chat build EXPLORE-1021C

Status: in progress (release lane, no new product code; branch crew/chat-release-1021c)

## Journey

The owner hand-tested the chat build EXPLORE-1021C on the explore copy (21 Oct 2026, 21:00 MYT) and said "merge and
release". This lane ships exactly that tree plus current main, with every new switch at its inert default, so prod
behaves as before for the gated parts until the owner switches them on.

## What ships

- Build: local branch `crew/explore-1021c` = fc24683609, which is #1809 (ee1e734bf2, chat release
  `claude/release-chat-1021-sppzcw`) + #1807 CHAT-INDEX-VIZ (bbb7183443) + #1814 promo A3 fix (bd37d90935) +
  CHAT-CLOSED-LISTS-L measurement code b46ecf2768 (lean v92 template file, stored parser reasoning setting,
  migration `lean_0001_parser_reasoning`) + main at build time (9bbb8fd7df).
- Merge of origin/main 9d19e2329b (#1815, #1818, #1817, #1813, #1715 already in). No conflicts.
- #1816 (REPORT-SMART) is OUT.

## Steps

1. Reset the lane branch to fc24683609, merge origin/main. Check: `git diff fc24683609 HEAD` equals
   `git diff 9bbb8fd7df origin/main` (the delta is main only). `alembic heads` prints one head.
2. Inert defaults, cited by file:line in the PR body: composer switch off, closed lists mode `block`, parser
   reasoning `off`; no migration or startup path moves the parser prompt production label.
3. Guards on a throwaway head DB (`scripts.bootstrap_env`, `-n 2` max): uuid principle, list pagination limit,
   parser prompt budget, serial `tests/test_migration_*.py` and `-m serial_ddl`, every backend test file the build
   touches vs main (the 12 known stale tests among them: 4 in `test_closed_lists_hidden_keys_paths.py`, 8
   composer-on round8 x5 / round9 x2 / hidden_keys b9_a_zero_set). No new failures.
4. PR to main titled "release(chat): EXPLORE-1021C owner-tested chat build": ungated changes, gated changes, owner
   prod steps after deploy, rollback, known gaps.

## Owner prod steps (after deploy)

(a) Settings > Chatbot: Reply composer ON, Closed lists Index; parser reasoning stays OFF.
(b) Prompts page: import v92 (`documentation/plans/chatbot/lean-index/parser-v92.txt`, explore pin 9ad4bf39),
    publish it as the production label.
(c) MCP redeploys with the backend (`blue_green_deploy.sh`): confirm.
Open question to crew: the explore DB the owner tested on also carried the LEAN data step
(`documentation/plans/chatbot/lean-index/PROD-OWNER-STEP.md`: photo alias words, "Spec" out of the Technical
Specifications description). Listed in the PR body as an owner step to match the tested data.

## Known gaps (owner accepted)

"drawing also" false "no drawing" claim, "See mre", "not discon", "Piture" scope.

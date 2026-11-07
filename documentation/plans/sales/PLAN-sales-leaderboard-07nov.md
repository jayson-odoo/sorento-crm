# PLAN: SALES-LEADERBOARD (sales leaderboard screen)

Status: Plan. Card asked on PR #2227 (7 Nov); no code until the owner answers. Track: full (size L, new screen).
Card: `CARD-sales-leaderboard-07nov.md`. UAC: `sales-leaderboard-07nov-acceptance-criteria.md` (after answers).

Owner 7 Nov ~15:40: "I also need a sales leaderboard feature. So let's think about it."

Fixed inputs:
- Sales = IV + CS + DN - CN net, by DocDate, not cancelled (owner 27 Oct, SALES-UNIFIED).
- One sales calculator: the REPORT-UNIFY engine (`services/reports/ask.run_ask`, invoiced basis). No second one.
- Targets / tiers / commission already exist (sales.targets, #2186); a salesperson sees only their own commission.

Mockup: `mockups/sales-leaderboard-07nov.html` (placeholder figures until the dev-copy SQL `evidence/sales-leaderboard-oct-dev.sql` is run by crew).

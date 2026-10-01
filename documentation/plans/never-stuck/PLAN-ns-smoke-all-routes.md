# PLAN: NS-SMOKE-ALL-ROUTES (Never-stuck guard G4)

Status: Plan (small fix track pending sizing; test + CI only, no migration, no product code beyond a data-testid marker)

Nightly Playwright smoke that opens every app route as admin, a restricted user and an expired
session, failing on stuck loading (15 s), expired session not on sign-in (5 s), refusal rendered
as empty, or raw permission text. Details follow in the next commit.

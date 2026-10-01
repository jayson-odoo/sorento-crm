# PLAN: AutoCount SO 'Transferable' flag; non-transferable SOs excluded from Stock Debt

Status: Plan (scouting). Track: TBD (has a migration, so not small-fix).

Lane: SO-TRANSFERABLE. Owner ask, 1 Oct 2026: AutoCount sales orders carry a header column
`Transferable` (T/F), e.g. SO421824 F, SO422024 F, SO422049 T, SO422051 T, SO422058 F. Pull it into
sorento-crm; SOs with Transferable = F must NOT be considered in Stock Debt.

Scout findings and design follow in the next commit.

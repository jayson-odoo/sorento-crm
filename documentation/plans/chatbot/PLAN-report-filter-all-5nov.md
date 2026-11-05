# PLAN: report filters - explicit ALL, parser object final

Status: Plan (lane REPORT-FILTER-ALL, track: standard, no migration). Started 5 Nov 2026.

Owner pain: "clear brand", "clear company", "all brands", "any agent", "clear all" fail or behave
randomly in the sales / outstanding report chatbot. Fix at the root: the parser's report object
is final; every filter slot has an explicit ALL value; code applies it as written with one generic
safety rule.

Details follow in later commits (behaviour card, deleted-rule ledger, test list).

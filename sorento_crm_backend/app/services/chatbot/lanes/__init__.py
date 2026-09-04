"""The per-branch-kind lanes. One module per lane, each ported from its n8n sub-workflow.

S4 lands the first one (`casual`, the `low_signal` branch). Every lane is a plain module
of functions over structured state: the engine decides WHICH lane runs, the lane decides
what the answer is, and neither reads the customer's raw words (D11 - that is the parser's
job and only the parser's).
"""

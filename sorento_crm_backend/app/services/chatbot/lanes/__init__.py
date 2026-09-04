"""The turn's lanes: one package per arm `route-turn` decides between.

Each is a plain module of functions over structured state - the engine decides WHICH lane
runs, the lane decides what the answer is, and neither reads the customer's raw words
(D11: that is the parser's job and only the parser's).
"""

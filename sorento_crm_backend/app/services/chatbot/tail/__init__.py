"""The tail of the turn: what this branch built, what to say, what to remember.

Four ported nodes, in the order `sub-output` runs them:

* `outcome.escalate_catalog` - `escalate-catalog.js`, the canned-copy switch;
* `member_offer` - `cs-roster-plan` + the team-members roster (in-process, no HTTP) +
  `build-cs-member-offer`;
* `outcome.build_outcome` - the 15-key producer map `compile-current-state` reads
  instead of sniffing 18 upstream nodes by name;
* `compile_state.compile_current_state` - 1,948 lines of JS: the reply ladder, every
  session key, and every carry lifecycle;
* `compose.crossdomain_compose` - folds the cross-domain block in and re-seals the reply.

Everything here is a PURE function over JSON. The only I/O in the tail is the roster
read and the session write, and both live in `engine.complete_turn`, so the replay
corpus can grade the logic without a database.
"""

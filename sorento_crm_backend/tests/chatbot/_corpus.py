"""Fixture corpus loader for the node-replay suite (AC-004).

Two sources, always both:

* the VENDORED subset under ``tests/fixtures/chatbot/nodes/<node>/*.json`` - committed,
  about 4 MB, one fixture per node per branch kind plus the regression guards and the
  named canaries. It grew past the original 3 MB note at S6a and the reason is worth
  stating: a resolve+gate capture carries the WHOLE resolver response in its `ctx`, and
  the `offer` exit carries it four times over (the item, `gate`, `ctx_resolved` and
  `ctx_resolved.ctx.gate`), so the smallest capture of that arm is 236 KB. The alternative
  was to stop grading the arm in CI, which is worse. Nothing over 400 KB is vendored.
  Each S6a node carries at least one capture from the 5 Sep run (`rg-*`, current bodies)
  and, where one exists under the size cap, one older capture as well - so CI grades both
  the two late-added keys AND the `keys_to_strip` path that excuses them. It runs
  everywhere, CI included, and it is what makes a red replay a merge blocker rather than a
  local curiosity.
* the FULL corpus in the sibling n8n checkout, pointed at by ``CHATBOT_FIXTURES_DIR``
  (default ``../../sorento_crm_n8n/n8n-workflows-init/tests/fixtures`` relative to the
  monorepo root). Absent = those tests skip with a message; present = every capture for
  a ported node replays.

**Only a REAL CAPTURE grades the port.** ``source.expected_from`` says where a fixture's
``expected`` came from: ``runData`` is what the node actually emitted in a real n8n
execution, ``reasoned`` is a hand-written expectation. The escalation-routing lane
hand-revised 31 ``reasoned`` ``output_exchange`` fixtures to encode the UNPROMOTED
B-TEAM-1' behaviour, under the SAME filenames, so a ``reasoned`` expectation can describe a
body that has never run in production. Grading against one would make an unpromoted lane
change a merge gate.

So: ``runData`` fixtures GRADE and a mismatch fails the suite; ``reasoned`` fixtures are
still loaded and still replayed, and their agreement is REPORTED as a count, but they never
fail. The same split applies to any worlds derivation. Measured on 5 Sep 2026 after the
re-port onto the live body: 782 ``runData`` files, all graded and green, and 152
``reasoned`` files of which 114 agree and 38 (19 distinct fixtures, vendored + full corpus)
pin B-TEAM-1'.

A fixture is the n8n harness's own shape::

    {source, ctx, input, expected, runIndex, execution, ran}

``ctx`` maps an upstream node name to the item list it emitted, ``input`` is the node's
own input item list, and ``expected`` is the normalised output item list. Comparison is
after a JSON round trip on both sides, exactly as ``tests/harness/n8n-shim.js``'s
``assertOutputEquals`` does it - an in-process ``undefined`` can never survive to n8n, so
it must not survive to the assertion either.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
VENDORED_ROOT = BACKEND_ROOT / "tests" / "fixtures" / "chatbot" / "nodes"

# The n8n checkout is a sibling of the monorepo root - but a lane runs from a git
# worktree several directories deeper, so the sibling is found by walking up rather than
# by counting parents (which is how this silently skipped in every worktree).
_CORPUS_SUFFIX = Path("sorento_crm_n8n") / "n8n-workflows-init" / "tests" / "fixtures"

# ...and the CAPTURE lane's worktree first, when it is there. The capture runs land in
# `captures-rs1a-parser` and reach the main n8n checkout only when that lane merges, so
# auto-discovery that stops at the main checkout grades a port against a corpus that is
# missing the captures the port was written from - measured: `miss-suggest-result` has
# captures in the worktree and none in the main checkout, so
# `test_full_corpus_has_at_least_one_capture[miss-suggest-result]` fails, and ONLY when
# `CHATBOT_FIXTURES_DIR` is unset. An explicit `CHATBOT_FIXTURES_DIR` still wins over
# both; this only changes what "found it myself" means.
_CORPUS_WORKTREE_SUFFIX = (
    Path("sorento_crm_n8n")
    / ".claude"
    / "worktrees"
    / "captures-rs1a-parser"
    / "n8n-workflows-init"
    / "tests"
    / "fixtures"
)

# Which capture slugs hold each ported node. A node can live under more than one slug
# (the live spine and the fail-closed clone capture the same node names), so the loader
# unions them and prefixes the fixture id with the slug to keep ids unique.
NODE_SLUGS: dict[str, tuple[str, ...]] = {
    "route-turn": ("clone-spine-RS", "spine-rs-1a", "live-spine-sorento-consume-main"),
    "build-ctx": ("clone-spine-RS", "spine-rs-1a", "live-spine-sorento-consume-main"),
    "output_exchange": ("sub-semantic-parser",),
    "suggest-follow-up": ("sub-semantic-parser",),
    # S6a - the business lane's resolve + gate. Two slugs that DO carry directories with
    # these names are deliberately absent, because the node they captured is not this one:
    # `sub-answer-rs/disallowed-entity-gate` and `sub-fetch-results-rs/{tier-gate,
    # build-ctx-resolved}` are RS-8 name-preserving STAND-INS (`return [{json: $json.gate}]`
    # and friends), whose input is their sub's trigger and whose expected is a re-emission.
    # Measured: the stand-in's expected has the gate's keys and its input has none of them.
    "disallowed-entity-gate": (
        "sub-resolve-and-gate-rs",
        "live-spine-sorento-consume-main",
        "clone-spine-RS",
    ),
    # `sub-fetch-results-live` ALSO has a directory called `tier-gate` (9 captures) and it is
    # deliberately absent: that node is another RS-6.2 name-preserving STUB, whose whole body
    # is `return [{ json: trigger.tier_gate }]`. Measured - its input is the sub's trigger
    # (`{ctx_resolved, tier_gate, is_test}`), its expected is the re-emitted `tier_gate`, and
    # nothing in it computes. Grading S6a's real `tier_gate.py` against it would fail on
    # every capture for a reason that says nothing about the port.
    "tier-gate": ("sub-resolve-and-gate-rs", "live-spine-sorento-consume-main", "clone-spine-RS"),
    "build-ctx-resolved": ("sub-resolve-and-gate-rs", "clone-spine-RS"),
    "annotate-incoming-picker": ("sub-resolve-and-gate-rs", "live-spine-sorento-consume-main"),
    "annotate-customer-picker": ("live-spine-sorento-consume-main",),
    "resolve-exit-continue": ("sub-resolve-and-gate-rs",),
    # S4 - the low_signal lane. Two slugs, and both are real captures of the same node:
    # the SPINE sees it through `Call 'sub-casual-llm'`, and `sub-casual-llm-live` is the
    # sub's own execution list (version 08bf56a5, pool fully scanned - see
    # `scripts/chatbot_fixture_coverage.py`'s CAPTURE_REPORT).
    "construct-user-prompt": ("live-spine-sorento-consume-main", "sub-casual-llm-live"),
    # `central-exchange` is the SAME name on two DIFFERENT node bodies, and only one of
    # them is the fence-stripping parse this lane ports. The three slugs registered are
    # that one: the SPINE (which sees the node through `Call 'sub-answer'`) plus
    # `sub-answer`'s own two execution lists.
    #   * `sub-answer{,-live,-rs}` - sha256 1ad9139d..., 28 lines, the parse;
    #   * `sub-send-attachments{,-rs}` - sha256 f7042838..., 12 lines, an RS-5 name-
    #     preserving stub that returns `attachments_src` off the trigger and has nothing to
    #     do with parsing anything.
    # The second pair is deliberately absent for the same reason S6a leaves its stand-ins
    # out above. Measured, not assumed: with both pairs registered the parse agrees on
    # 13/13 `sub-answer`-family fixtures and on 1/4 of the attachment ones, and the one
    # graded (`runData`) mismatch is `sub-send-attachments-rs/rs51-02-withattach`, whose
    # `input` is `[{"json": {}}]` while its `expected` is a fully composed answer - the
    # signature of a node reading something other than its own input.
    # S5 - the escalation lane. Four nodes, one slug: the LIVE `sub-escalation`
    # (`fr2u3e6FKg52cPvK` @ `bac9613b`, the 10-node graph). The EXPORT of that workflow
    # carries a `fresh-entity-gate` and a `clarify-team-*` pair that are NOT live (B-HB-1 /
    # B-TEAM-1', unpromoted), which is why the port and these captures both come from the
    # live body and not from it. `clarify-company-reply` has ZERO captures: the clarify arm
    # did not fire once in the window, honestly reported rather than fabricated.
    "escalation-input": ("sub-escalation-live",),
    "escalation-context": ("sub-escalation-live",),
    "clarify-company-reply": ("sub-escalation-live",),
    "escalation-result": ("sub-escalation-live",),
    "central-exchange": (
        "live-spine-sorento-consume-main",
        "sub-answer-live",
        "sub-answer-rs",
    ),
    "resolve-exit-offer": ("sub-resolve-and-gate-rs",),
    "resolve-exit-not-found": ("sub-resolve-and-gate-rs",),
    "item": ("sub-resolve-and-gate-rs",),
    # Synthetic: the WHOLE sub replayed from a captured trigger, graded against the exit
    # arm's own capture. It reuses the `resolve-exit-*` directories rather than having one
    # of its own, so no fixture is invented - see `sub_run_fixtures()`.
    "sub-resolve-and-gate": (),
    # S6b - `sub-fetch-results`'s own nodes (AC-605, AC-606). Captured under ONE slug,
    # `sub-fetch-results-rs`. `tier-gate` / `build-ctx` / `build-ctx-resolved` ALSO have
    # directories inside this slug (the RS-8 name-preserving stand-ins the S6a comment
    # above already excludes for the same reason: their input is the sub's own trigger and
    # their expected is a re-emission, not that node's real body), so they are deliberately
    # NOT re-registered here under this slug.
    # The 5 Sep batch-3 run added `sub-fetch-results-live` (the LIVE sub, 96 files) beside
    # the older `-rs` fork, and `sub-get-results` / `sub-get-rag-live` for the two subs the
    # fetch step calls.
    "tool-filter": ("sub-fetch-results-rs", "sub-fetch-results-live"),
    "tier-probe-plan": ("sub-fetch-results-rs", "sub-fetch-results-live"),
    "tier-probe-collect": ("sub-fetch-results-rs", "sub-fetch-results-live"),
    "fetch-result": ("sub-fetch-results-rs", "sub-fetch-results-live"),
    "entity-ids-transformer": ("sub-get-results",),
    "output-structurer": ("sub-get-results",),
    # `sub-get-rag`'s two Code nodes, under the names n8n gave them. Ported for REPLAY: in
    # process there is no SQL to bind parameters for, and the collapse is what makes
    # `tool-filter`'s max-similarity pick meaningful.
    "Code_in_JavaScript": ("sub-get-rag-live",),
    "Code_in_JavaScript1": ("sub-get-rag-live",),
    # S2, the tail. `clone-sub-output` is the RS-9 split-out sub; the two spine slugs
    # captured the same node names before and after the split, which is why the loader
    # unions them and prefixes each id with its slug.
    # `sub-output-live` is the SHIPPING body captured from live (`qa4LWvPrhUnAPgjC`,
    # version `c32698c1`), which is the body the port implements - so unlike the
    # spine slugs it grades the port against itself rather than against an older
    # deployment, and it is where the tail's real coverage comes from.
    "build-outcome": ("sub-output-live", "clone-sub-output", "clone-spine-RS"),
    "escalate-catalog": (
        "sub-output-live",
        "live-spine-sorento-consume-main",
        "clone-spine-RS",
    ),
    "cs-roster-plan": ("sub-output-live", "live-spine-sorento-consume-main"),
    "build-cs-member-offer": ("sub-output-live", "live-spine-sorento-consume-main"),
    "compile-current-state": (
        "sub-output-live",
        "live-spine-sorento-consume-main",
        "clone-spine-RS",
    ),
    "crossdomain-compose": (
        "sub-output-live",
        "live-spine-sorento-consume-main",
        "clone-spine-RS",
    ),
    # S6c - the business lane's answer + miss half (AC-607, AC-608). Registered here so
    # gate 0's report (`scripts/chatbot_fixture_coverage.py`) can SEE these cells; the
    # replay itself is parametrised in `tests/chatbot/test_s6c_answer_lane.py`, which
    # keeps its own copy of this map because it loads the same shape directly.
    #
    # Two slugs are deliberately absent from the pairs they look like they belong to:
    # `sub-send-attachments{,-rs}` carries a DIFFERENT 12-line `central-exchange` (a
    # name-preserving stub re-emitting `attachments_src`), and `sub-answer{-rs,-live}`
    # carries a 12-line `build-result` that is a named-value carrier, not
    # `sub-main-processing`'s real 88-line node. Same class as S6a's stand-in exclusions.
    "validator": ("live-spine-sorento-consume-main",),
    "promo-picker": ("live-spine-sorento-consume-main",),
    "crossdomain-zeroset": ("live-spine-sorento-consume-main",),
    "crossdomain-render": ("live-spine-sorento-consume-main",),
    "not-found-error-message": ("live-spine-sorento-consume-main",),
    "access-level-choice-message": ("clone-spine-RS", "live-spine-sorento-consume-main"),
    "build-suggest-offer": ("live-spine-sorento-consume-main",),
    "build-result": (
        "clone-sub-main-processing",
        "clone-spine-RS",
        "live-spine-sorento-consume-main",
    ),
    "answer-input": ("sub-answer-rs", "sub-answer-live"),
    "answer-result": ("sub-answer-rs", "sub-answer-live"),
    "miss-roster-check": (
        "clone-spine-RS",
        "live-spine-sorento-consume-main",
        "sub-answer",
        "sub-answer-rs",
        "sub-answer-live",
    ),
    "miss-roster-plan": ("live-spine-sorento-consume-main", "sub-answer-live"),
    "build-miss-member-offer": ("live-spine-sorento-consume-main", "sub-answer-live"),
    "dym-transform-partial": (
        "live-spine-sorento-consume-main",
        "sub-answer-rs",
        "sub-answer-live",
    ),
    "dym-annotate-partial": ("live-spine-sorento-consume-main", "sub-answer-live"),
    "dym-transform": (
        "clone-spine-RS",
        "live-spine-sorento-consume-main",
        "sub-miss-suggest-rs",
        "sub-miss-suggest-live",
    ),
    "dym-annotate": (
        "clone-spine-RS",
        "live-spine-sorento-consume-main",
        "sub-miss-suggest-rs",
        "sub-miss-suggest-live",
    ),
    # `sub-miss-suggest`'s OWN exit/carrier (RS-7 errata) - only ever captured inside the
    # sub, never on the spine, which inlines everything and has no boundary to carry across.
    "miss-suggest-result": ("sub-miss-suggest-live",),
    # `promo-dym-plan` exists in the export and fired ZERO times in the scanned pool. It is
    # a real zero cell, not an oversight: the promotion did-you-mean lane needs a promotion
    # miss WITH candidates, and the 232-execution pool held none.
    "promo-dym-plan": ("sub-miss-suggest-live",),
    "sibling-transform": ("sub-miss-suggest-live", "sub-miss-suggest-rs"),
}

# Output keys the SHIPPING node bodies emit that the body an OLD capture was taken
# against could not. NOT divergences - the port agrees with the export, and those captures
# grade an older body - and not staleness either: everything else about them still grades.
#
# **Applied per FIXTURE, not per node, and derived from the capture itself.** The 5 Sep
# capture run (84 files, live sub `tKeQUkZK5cFK9BFa` version `4f367b1c`) was taken against
# the current bodies and DOES carry both keys, so those captures grade them like any other
# field. `keys_to_strip` therefore drops a key only from a capture whose `expected` does
# not contain it anywhere - which is exactly "this capture predates the key" and cannot go
# stale the way a hard-coded version list would. Both keys are emitted unconditionally by
# the shipping bodies, so "absent from expected" has no other possible cause.
#
# Evidence for the two keys, direct and reproducible (n8n repo `git show <rev>:...`):
#
# * the 31 Aug `sub-resolve-and-gate*` captures carry `workflow_version` 70fa92bf and the
#   export ships 43a37c05; every `live-spine-sorento-consume-main` capture ran the spine's
#   own 934-line copy of the gate;
# * `f1cee5b` (2026-08-31) is that 934-line body, `a4da785` + `f4c8f02` (2026-09-01) are
#   the two commits that added these keys - `out.specific_options` (RS-9 Fix 5) and
#   `tier_pick_domain` (RS-9 Fix 8);
# * diffing the two bodies gives FIVE changes, and only these two are unconditional. The
#   other three (a `company` key inside `specific_options`, the F16 company-suffixed label,
#   and the `_dfSpecAnswered` refinement of the dropped-filter gate) are reachable only
#   through inputs the older captures do not contain.
# `display_name` on the gate's entities is the ONE key here that the n8n body will never
# emit, rather than one it emits since a later commit. It is a CRM addition, and it is the
# fix for a defect the customer reads: `canonical_code` for a customer is the ACCOUNT code
# or the denormalised `debtor_name`, so the not-found line printed "no order records found
# for 300-H070, RPACC" at a customer who has never seen that string
# (`fetch._axis_labelled_subject`, `gate._display_name`). Registered on the same mechanism
# because it is the same GRADING problem - the capture cannot carry a key the port emits -
# and because the alternative, a blanket `Divergence`, would stop grading these 243 gate
# captures entirely instead of grading everything except this key.
#
# MEASURED over the whole corpus on 6 Sep 2026: `display_name` appears in 0 of the 3258
# full-corpus fixture files and 0 of the 240 vendored ones, so nothing anywhere is masked
# by this entry today and the strip is a pure no-op on every node that does not emit it.
# (An earlier revision of this comment said 934, which was a subset count.) 12 gate captures replay
# differently without it (the 9 `live-spine-sorento-consume-main` and 3 `clone-spine-RS` /
# `sub-resolve-and-gate-rs` turns that name a customer); the trigger to revisit is n8n
# emitting a key by this name of its own.
CAPTURE_BODY_ADDITIONS: dict[str, tuple[str, ...]] = {
    "disallowed-entity-gate": ("specific_options", "display_name"),
    "tier-gate": ("tier_pick_domain",),
    # S8a, AC-808: the ten entries that used to sit in `STALE_FIXTURES` are graded here
    # instead of skipped. Both groups are the same class as the two keys above - a key
    # the SHIPPING body emits that the body the capture ran against could not - so they
    # belong on this mechanism rather than on an exclusion list.
    #
    # `build-ctx` / `media` (the four RS-2 captures). The live body writes the key
    # UNCONDITIONALLY: `export/{live-spine-sorento-consume-main,clone-spine-RS,
    # spine-rs-1a}/nodes/build-ctx.js` line 47 is `media: $('media-intake').first().json
    # .media`, inside the one object literal the node returns, with no branch above it,
    # and its own comment names RS-4 cut 1 as when it arrived. So "absent from expected"
    # has exactly one cause. Measured over the whole corpus (118 captures): 114 carry
    # `media`, 4 do not, and those 4 are precisely the RS-2 entries.
    "build-ctx": ("media",),
    # `compile-current-state` / `tier_menu` (the six RS-9 Fix 6 captures). This one is
    # CONDITIONAL - `export/sub-output-live/nodes/compile-current-state.js` lines 1266 to
    # 1277 end in `if (_tierMenu) output.variables.tier_menu = _tierMenu;`, so an ordinary
    # turn emits nothing and "absent from expected" could in principle also mean "the port
    # wrongly emitted it". That is why the disposition is measured rather than argued.
    # Over all 261 captures for this node: 1 carries `tier_menu` on BOTH sides (graded, not
    # stripped - the 4 Sep `sub-output-live` run, `out-14871227`, workflow version
    # c32698c1), 254 carry it on NEITHER (the strip is a no-op), 0 carry it on the expected
    # side alone, and the 6 where the port emits it and the capture does not are exactly
    # the six former `STALE_FIXTURES` names. Nothing else in the corpus is masked by this
    # entry today; the trigger to revisit is a new capture appearing in the "port only"
    # column that is NOT one of those six.
    "compile-current-state": ("tier_menu",),
    # These carry the gate's / tier-gate's item onwards, so an old capture of them is
    # missing the same keys one or more levels down.
    "build-ctx-resolved": ("specific_options", "display_name"),
    "annotate-incoming-picker": ("specific_options", "display_name"),
    "annotate-customer-picker": ("specific_options", "display_name"),
    "resolve-exit-continue": ("specific_options", "tier_pick_domain", "display_name"),
    "resolve-exit-access-ask": ("specific_options", "tier_pick_domain", "display_name"),
    "resolve-exit-not-found": ("specific_options", "tier_pick_domain", "display_name"),
    "resolve-exit-offer": ("specific_options", "tier_pick_domain", "display_name"),
    "sub-resolve-and-gate": ("specific_options", "tier_pick_domain", "display_name"),
}


def _contains_key(value, key: str) -> bool:
    """Does `key` appear anywhere in this structure?"""
    if isinstance(value, dict):
        if key in value:
            return True
        return any(_contains_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_contains_key(v, key) for v in value)
    return False


def keys_to_strip(node: str, expected) -> tuple[str, ...]:
    """The body-addition keys THIS capture predates, i.e. the ones it cannot grade."""
    return tuple(
        key for key in CAPTURE_BODY_ADDITIONS.get(node, ()) if not _contains_key(expected, key)
    )


def strip_keys(value, keys: tuple[str, ...]):
    """Drop `keys` at every depth.

    Recursive because the exit arms carry the gate's and tier-gate's items nested under
    `gate` / `ctx_resolved` / `tier_gate`, so a top-level-only strip would leave the same
    delta three levels down and grade nothing.
    """
    if not keys:
        return value
    if isinstance(value, dict):
        return {k: strip_keys(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [strip_keys(v, keys) for v in value]
    return value


# Fixtures pinned to a node body that is NOT the one production runs. They are not
# divergences - nothing about the port disagrees with the live body - and they do not
# belong in `divergences.py`, which is reserved for deliberate hazard fixes.
#
# **What changed on 5 Sep 2026.** The port was made from the working-tree EXPORT of
# `sub-semantic-parser`, whose MANIFEST is flagged `locally_edited`. The n8n partner
# session then fetched the LIVE body read-only: 1,881 lines, sha `a837333a13a2`, saved at
# `output_exchange.live.js` in that session's scratchpad with
# `output_exchange.LIVE-vs-WORKTREE.diff` beside it. The export carries an UNPROMOTED lane
# change (B-TEAM-1': `routing.team_source`, a 4-rank team ladder replacing the
# `?? 'customer_service'` default, a `resource_attachment` routing row, a pending
# `team_clarify` completion block, and a state-only company-pick resolver with the
# deterministic word-match tier deleted; +241/-83 over 10 hunks). `head/output_exchange.py`
# was re-ported onto the LIVE body, and the five `parser-*` entries that used to sit here
# all replay EQUAL again - they were LIVE-faithful captures being graded against the wrong
# body, which is exactly the tell.
#
# **The mirror-image set is NOT listed here.** The 19 hand-written fixtures that pin the
# unpromoted body are handled structurally instead, by `expected_from` (see the module
# docstring): they are `reasoned`, so they are replayed and reported and never graded. A
# name list would have to be maintained by hand and would go stale the moment the lane adds
# another; the field is already on every fixture and says exactly the right thing.
#
# **`STALE_FIXTURES` is EMPTY as of S8a (AC-808)**, and it stays a declaration rather
# than being deleted, because the mechanism is still the right answer for the next
# genuinely ungradeable capture. The ten entries it used to hold - four `build-ctx`
# captures predating the RS-4 `media` key and six `compile-current-state` captures
# predating the RS-9 Fix 6 `tier_menu` block - were not staleness of a kind that had to
# cost coverage: each was a capture that could not emit ONE key the shipping body emits,
# which is exactly what `CAPTURE_BODY_ADDITIONS` is for. They now grade everything except
# that key, with the live body cited and the corpus-wide footprint measured, at the two
# entries added there.
#
# What still belongs here: a capture whose body differs in a way that cannot be reduced
# to a set of added keys (a changed VALUE, a different branch taken). Those are SKIPPED,
# not dropped - `test_replay.py` emits one skip per entry with its reason, so `pytest -rs`
# and the summary count show how much is not graded.
STALE_FIXTURES: dict[tuple[str, str], str] = {}


def stale_entries() -> list[tuple[str, str, str]]:
    """`(node, fixture, reason)` for every registered stale capture, sorted."""
    return sorted((node, name, reason) for (node, name), reason in STALE_FIXTURES.items())


@dataclass(frozen=True)
class Fixture:
    node: str
    name: str
    path: Path
    data: dict

    @property
    def expected_from(self) -> str:
        """`runData` (a real execution) or `reasoned` (hand written). See the module
        docstring: only `runData` grades."""
        return (self.data.get("source") or {}).get("expected_from") or "runData"

    @property
    def graded(self) -> bool:
        return self.expected_from == "runData"

    @property
    def ctx(self) -> dict:
        return self.data.get("ctx") or {}

    @property
    def input(self) -> list:
        return self.data.get("input") or []

    @property
    def expected(self) -> list:
        return self.data.get("expected") or []

    def upstream(self, node_name: str) -> list:
        """The item list a named upstream node emitted, or [] when it did not run."""
        return self.ctx.get(node_name) or []

    def first(self, node_name: str) -> dict:
        """``$('node').first().json`` - raises the way the n8n shim does when unstubbed."""
        items = self.upstream(node_name)
        if not items:
            raise KeyError(
                f"$('{node_name}').first(): zero items in fixture {self.name} "
                f"(known: {', '.join(sorted(self.ctx))})"
            )
        return items[0].get("json")


def corpus_root() -> Path | None:
    """The full n8n corpus root, or None when this checkout has no sibling n8n repo."""
    raw = os.environ.get("CHATBOT_FIXTURES_DIR")
    if raw:
        root = Path(raw).expanduser()
        return root if (root / "nodes").is_dir() else None
    for ancestor in BACKEND_ROOT.parents:
        for suffix in (_CORPUS_WORKTREE_SUFFIX, _CORPUS_SUFFIX):
            candidate = ancestor / suffix
            if (candidate / "nodes").is_dir():
                return candidate
    return None


def corpus_skip_reason() -> str:
    return (
        "full n8n fixture corpus not found - set CHATBOT_FIXTURES_DIR to "
        "<n8n checkout>/n8n-workflows-init/tests/fixtures (the vendored subset still ran)"
    )


def _load_dir(node: str, directory: Path, prefix: str = "") -> list[Fixture]:
    if not directory.is_dir():
        return []
    out: list[Fixture] = []
    for path in sorted(directory.glob("*.json")):
        if (node, path.stem) in STALE_FIXTURES:
            continue
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        out.append(Fixture(node=node, name=f"{prefix}{path.stem}", path=path, data=data))
    return out


def vendored(node: str) -> list[Fixture]:
    """The committed subset for one node. Always runs."""
    return _load_dir(node, VENDORED_ROOT / node)


def graded(fixtures: list[Fixture]) -> list[Fixture]:
    """The real captures. A mismatch on one of these fails the suite."""
    return [f for f in fixtures if f.graded]


def reasoned(fixtures: list[Fixture]) -> list[Fixture]:
    """Hand-written expectations. Replayed and counted, never a gate."""
    return [f for f in fixtures if not f.graded]


def full_corpus(node: str) -> list[Fixture]:
    """Every capture for one node across its slugs. Empty when the corpus is absent."""
    root = corpus_root()
    if root is None:
        return []
    out: list[Fixture] = []
    for slug in NODE_SLUGS.get(node, ()):  # noqa: B007 - explicit slug list, not discovery
        out.extend(_load_dir(node, root / "nodes" / slug / node, prefix=f"{slug}/"))
    return out


def json_round_trip(value):
    """What n8n's own comparison does to both sides before diffing them."""
    return json.loads(json.dumps(value))


def declared_branches(node: str) -> tuple[str, ...]:
    """Every branch this node CAN produce, whether or not anything captured it.

    Seeded into the coverage matrix so an arm nobody has ever captured is a visible zero
    rather than an absent row - which is exactly the cell gate 0 exists to surface. Only
    `route-turn` has a closed vocabulary; the parser nodes are cut by domain, and the set
    of domains a capture window happens to contain is not a contract.

    Lives here rather than in `scripts/chatbot_fixture_coverage.py` because this file is
    inside the module's import boundary (AC-002) and the script is not.
    """
    if node == "route-turn":
        from app.services.chatbot.contracts import BRANCH_KINDS

        return BRANCH_KINDS
    if node in ("sub-resolve-and-gate", "resolve-exit-access-ask"):
        # The sub's exits ARE a closed vocabulary (`resolve-arm`'s four Switch arms), and
        # one of them - `access_ask` - has never been captured in any slug. Seeded so that
        # reads as a zero rather than as an absent row.
        from app.services.chatbot.contracts import EXIT_KINDS

        return EXIT_KINDS
    if node in ("cs-roster-plan", "build-cs-member-offer"):
        # Seeded so the two arms live has never reached are VISIBLE zeros. The
        # multi-company grouped renderer and the empty-roster fallback are the parts of
        # `build_cs_member_offer` most likely to be wrong and least likely to be
        # captured, and an `all` cell reading "met" said nothing about either.
        return ("single_company", "multi_company", "empty_roster")
    if node == "escalate-catalog":
        # The nine arms of its own `switch`. Seeded so a copy arm nobody has captured is
        # a visible zero rather than an absent row - which for a node whose whole job is
        # customer-facing wording is exactly the cell that matters.
        return (
            "not_found",
            "access_choice",
            "demand_qty",
            "not_supported",
            "clarify_menu",
            "escalate_offer",
            "out_of_scope",
            "escalation_declined",
            "offer_hold",
        )
    return ()


# The `resolve-exit-*` directories every whole-sub replay is built from. One capture per
# exit arm per turn, and each one carries the trigger, the resolver response and any probe
# response in its own `ctx`, so the sub can be run end to end with nothing stubbed by hand.
SUB_RUN_SOURCE_NODES = (
    "resolve-exit-continue",
    "resolve-exit-offer",
    "resolve-exit-not-found",
    "resolve-exit-access-ask",
)


def sub_run_fixtures(*, vendored_only: bool) -> list[Fixture]:
    """Every `resolve-exit-*` capture, relabelled as a whole-sub replay.

    `node` is rewritten to `sub-resolve-and-gate` so the divergence register and the
    body-addition strip key on the thing being graded (the sub) rather than on the
    directory the JSON happens to live in.
    """
    out: list[Fixture] = []
    for node in SUB_RUN_SOURCE_NODES:
        source = vendored(node) if vendored_only else full_corpus(node)
        for fixture in source:
            out.append(
                Fixture(
                    node="sub-resolve-and-gate",
                    name=f"{node}/{fixture.name}",
                    path=fixture.path,
                    data=fixture.data,
                )
            )
    return out

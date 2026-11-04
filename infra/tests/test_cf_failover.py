"""Unit tests for the failover controller's decisions (HA-CF-FAILOVER).

Plan: documentation/plans/infra/PLAN-ha-cf-failover-04nov.md section 3 (rules P1-P4, S1-S3,
D1-D2); UAC: documentation/plans/infra/ha-cf-failover-acceptance-criteria.md.

`decide()` is pure: no Postgres, no Cloudflare, no clock. These tests drive it tick by tick, and
the last group runs BOTH nodes against a small world model to check that no fault sequence ever
leaves two writable databases.

Run: python3 -m pytest infra/tests -q
"""

from __future__ import annotations

import random
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cf_failover import Config, ConfigError, Obs, decide, initial_state  # noqa: E402

TICK = 15
MB = 1024 * 1024


def cfg(**env):
    base = {"NODE_NAME": "crm-a", "PEER_NAME": "crm-b"}
    base.update({k: str(v) for k, v in env.items()})
    return Config.from_env(base)


def obs(**kw):
    d = dict(
        self_pg="standby", self_streaming=False, self_lsn=1000,
        peer_pg="unreachable", peer_lsn=None,
        cf_self="unhealthy", cf_peer="unhealthy", sync_names="",
    )
    d.update(kw)
    return Obs(**d)


def kinds(actions):
    return [a[0] for a in actions]


def run(c, o, seconds, start=0.0, state=None, step=TICK):
    """Feed the same observation (or obs(t) when callable) every tick. Returns (state, [(t, actions)])."""
    state = state if state is not None else initial_state()
    out = []
    t = start
    while t <= start + seconds:
        cur = o(t) if callable(o) else o
        state, actions = decide(state, cur, t, c)
        if actions:
            out.append((t, actions))
        t += step
    return state, out


def first(out, kind):
    for t, actions in out:
        if kind in kinds(actions):
            return t
    return None


# ---------------------------------------------------------------- config


def test_defaults_derive_from_the_cloudflare_check():
    c = cfg()
    assert (c.cf_check_interval, c.cf_consecutive_down) == (60, 2)
    assert c.fence_after == 240
    assert c.promote_after == 420
    assert c.fence_hold == 600
    assert c.app_sick_after == 900
    assert c.sync_mode == "off"


def test_faster_cloudflare_check_shrinks_the_windows_but_keeps_the_margin():
    c = cfg(CF_CHECK_INTERVAL=15)
    assert c.fence_after == 60
    assert c.promote_after == 240  # 60 + the 180 s floor


def test_app_sick_window_is_a_config_value():
    assert cfg(APP_SICK_AFTER=600).app_sick_after == 600


@pytest.mark.parametrize("env", [
    {"FENCE_AFTER": 240, "PROMOTE_AFTER": 400},          # margin under 180 s
    {"FENCE_HOLD": 300},                                  # hold must outlast the promote wait
    {"SYNC_MODE": "on"},                                  # unknown mode
    {"PEER_NAME": "crm-a"},                               # peer is itself
])
def test_config_refuses_an_unsafe_setup(env):
    with pytest.raises(ConfigError):
        cfg(**env)


# ---------------------------------------------------------------- S1 promote


def test_standby_promotes_after_promote_after_of_all_three_conditions():
    c = cfg()
    _, out = run(c, obs(), 600)
    t = first(out, "promote")
    assert t is not None and c.promote_after <= t < c.promote_after + TICK


def test_standby_never_promotes_on_an_unknown_cloudflare_answer():
    _, out = run(cfg(), obs(cf_peer="unknown"), 7200)
    assert first(out, "promote") is None


def test_standby_never_promotes_while_cloudflare_says_the_peer_is_healthy():
    _, out = run(cfg(), obs(cf_peer="healthy"), 7200)
    assert first(out, "promote") is None


def test_standby_never_promotes_while_streaming():
    _, out = run(cfg(), obs(self_streaming=True), 7200)
    assert first(out, "promote") is None


def test_standby_never_promotes_while_the_peer_postgres_answers():
    # Peer answers as primary but the stream is down: rejoin, never promote.
    _, out = run(cfg(), obs(peer_pg="primary", peer_lsn=1000), 7200)
    assert first(out, "promote") is None
    assert first(out, "rejoin") is not None


def test_a_break_in_any_condition_restarts_the_wait():
    c = cfg()

    def o(t):
        return obs(cf_peer="unknown") if 300 <= t < 315 else obs()

    _, out = run(c, o, 700)
    t = first(out, "promote")
    assert t is not None and t >= 315 + c.promote_after


def test_standby_too_far_behind_never_promotes_and_alerts():
    c = cfg()
    state, _ = run(c, obs(self_streaming=True, peer_pg="primary", peer_lsn=1000 + 20 * MB), 30)
    _, out = run(c, obs(self_lsn=1000), 1200, start=45, state=state)
    assert first(out, "promote") is None
    alerts = [a for _, acts in out for a in acts if a[0] == "alert"]
    assert alerts and "behind" in alerts[0][1]
    assert len(alerts) == 1  # once, not every tick


def test_promotion_survives_a_controller_restart_through_the_state():
    c = cfg()
    state, out = run(c, obs(), 300)
    assert first(out, "promote") is None
    _, out = run(c, obs(), 200, start=315, state=state)
    t = first(out, "promote")
    assert t is not None and t < 315 + c.promote_after


# ---------------------------------------------------------------- S2 rejoin, S3 both standby


def test_standby_rejoins_a_reachable_primary_it_cannot_stream_from():
    c = cfg()
    _, out = run(c, obs(peer_pg="primary", peer_lsn=5000, cf_peer="healthy"), 400)
    t = first(out, "rejoin")
    assert t is not None and c.rejoin_after <= t < c.rejoin_after + TICK
    # retried, not every tick
    assert sum(1 for _, a in out if "rejoin" in kinds(a)) <= 400 // c.rejoin_after + 1


def test_streaming_standby_does_nothing():
    _, out = run(cfg(), obs(self_streaming=True, peer_pg="primary", peer_lsn=1000, cf_peer="healthy"), 3600)
    assert out == []


def test_both_standby_the_one_further_ahead_promotes():
    c = cfg()
    _, ahead = run(c, obs(peer_pg="standby", self_lsn=2000, peer_lsn=1000), 120)
    _, behind = run(c, obs(peer_pg="standby", self_lsn=1000, peer_lsn=2000), 600)
    t = first(ahead, "promote")
    assert t is not None and c.both_standby_after <= t < c.both_standby_after + TICK
    assert first(behind, "promote") is None


def test_both_standby_tie_goes_to_the_lower_name():
    a = cfg()
    b = cfg(NODE_NAME="crm-b", PEER_NAME="crm-a")
    _, out_a = run(a, obs(peer_pg="standby", self_lsn=1000, peer_lsn=1000), 120)
    _, out_b = run(b, obs(peer_pg="standby", self_lsn=1000, peer_lsn=1000), 600)
    assert first(out_a, "promote") is not None
    assert first(out_b, "promote") is None


# ---------------------------------------------------------------- P1 lease, P2 app sick, P3, P4


def prim(**kw):
    d = dict(self_pg="primary", self_streaming=False, peer_pg="unreachable", cf_self="unhealthy", cf_peer="unhealthy")
    d.update(kw)
    return obs(**d)


def test_primary_fences_when_neither_cloudflare_nor_the_peer_has_seen_it():
    c = cfg()
    _, out = run(c, prim(), 600)
    t = first(out, "fence")
    assert t is not None and c.fence_after <= t < c.fence_after + TICK


def test_primary_on_unknown_cloudflare_also_fences_when_alone():
    c = cfg()
    _, out = run(c, prim(cf_self="unknown"), 600)
    assert first(out, "fence") is not None


def test_primary_keeps_writing_while_the_peer_streams_even_if_cloudflare_is_down():
    _, out = run(cfg(), prim(cf_self="unknown", self_streaming=True, peer_pg="standby"), 7200)
    assert first(out, "fence") is None


def test_link_cut_alone_never_fences_a_primary_cloudflare_sees():
    _, out = run(cfg(), prim(cf_self="healthy"), 7200)
    assert first(out, "fence") is None


def test_fence_precedes_any_possible_promotion_with_the_margin():
    c = cfg()
    _, out = run(c, prim(), 1200)
    assert first(out, "fence") + c.fence_margin <= c.promote_after


def test_app_sick_primary_fences_after_the_window_and_alerts():
    c = cfg()
    _, out = run(c, prim(self_streaming=True, peer_pg="standby"), 1200)
    t = first(out, "fence")
    assert t is not None and c.app_sick_after <= t < c.app_sick_after + TICK
    acts = dict(out)[t]
    assert any(a[0] == "alert" for a in acts)
    assert any(a[0] == "fence" and "app" in a[1] for a in acts)


def test_app_sick_needs_a_positive_unhealthy_report():
    _, out = run(cfg(), prim(cf_self="unknown", self_streaming=True, peer_pg="standby"), 7200)
    assert first(out, "fence") is None


def test_app_sick_fence_at_most_once_per_cooldown():
    c = cfg()
    state, out = run(c, prim(self_streaming=True, peer_pg="standby"), 1000)
    assert first(out, "fence") is not None
    # Later the node leads again (it rejoined, then won a both-standby) and is sick again.
    state, out = run(c, prim(self_streaming=True, peer_pg="standby"), 3600, start=5000, state=state)
    assert first(out, "fence") is None
    _, out = run(c, prim(self_streaming=True, peer_pg="standby"), 1200, start=100000, state=state)
    assert first(out, "fence") is not None


def test_two_primaries_alert_and_the_one_cloudflare_does_not_see_fences():
    c = cfg()
    _, out = run(c, prim(peer_pg="primary", cf_self="unhealthy"), 30)
    assert "fence" in kinds(out[0][1]) and "alert" in kinds(out[0][1])
    _, out = run(c, prim(peer_pg="primary", cf_self="healthy"), 30)
    assert "alert" in kinds(out[0][1]) and first(out, "fence") is None


def test_sync_mode_follows_the_stream_and_drops_the_moment_it_stops():
    c = cfg(SYNC_MODE="remote_write")
    s = initial_state()
    s, a = decide(s, prim(cf_self="healthy", self_streaming=True, peer_pg="standby"), 0, c)
    assert ("set_sync", "crm-b") in a
    s, a = decide(s, prim(cf_self="healthy", self_streaming=True, peer_pg="standby", sync_names="crm-b"), 15, c)
    assert not any(x[0] == "set_sync" for x in a)
    s, a = decide(s, prim(cf_self="healthy", self_streaming=False, sync_names="crm-b"), 30, c)
    assert ("set_sync", "") in a


def test_sync_mode_off_keeps_the_names_empty():
    c = cfg()
    _, a = decide(initial_state(), prim(cf_self="healthy", self_streaming=True, sync_names="crm-b"), 0, c)
    assert ("set_sync", "") in a
    _, a = decide(initial_state(), prim(cf_self="healthy", self_streaming=True), 0, c)
    assert not any(x[0] == "set_sync" for x in a)


# ---------------------------------------------------------------- D1, D2


def test_a_down_node_that_did_not_fence_starts_as_a_standby_at_once():
    _, a = decide(initial_state(), obs(self_pg="down", cf_self="healthy", peer_pg="unreachable"), 0, cfg())
    assert kinds(a) == ["start_standby"]


def test_fenced_node_rejoins_a_primary_peer_at_once():
    c = cfg()
    state, _ = run(c, prim(), 300)  # fences at 240
    _, a = decide(state, obs(self_pg="down", peer_pg="primary", peer_lsn=9000, cf_peer="healthy"), 330, c)
    assert "rejoin" in kinds(a)


def test_fenced_node_waits_the_hold_before_starting_beside_a_standby_peer():
    c = cfg()
    state, out = run(c, prim(), 300)
    fenced = first(out, "fence")
    _, out = run(c, obs(self_pg="down", peer_pg="standby", peer_lsn=1000, cf_peer="unhealthy"), 1200, start=fenced + TICK, state=state)
    t = first(out, "start_standby")
    assert t is not None and fenced + c.fence_hold <= t < fenced + c.fence_hold + TICK


def test_fenced_node_with_an_unreachable_peer_needs_cloudflare_to_say_it_is_down():
    c = cfg()
    state, out = run(c, prim(), 300)
    fenced = first(out, "fence")
    _, out = run(c, obs(self_pg="down", cf_peer="unknown"), 7200, start=fenced + TICK, state=state)
    assert first(out, "start_standby") is None
    _, out = run(c, obs(self_pg="down", cf_peer="healthy"), 7200, start=fenced + TICK, state=state)
    assert first(out, "start_standby") is None
    _, out = run(c, obs(self_pg="down", cf_peer="unhealthy"), 1200, start=fenced + TICK, state=state)
    assert first(out, "start_standby") is not None


# ---------------------------------------------------------------- both nodes, one world


class World:
    """Two nodes, a link, each node's public reachability, and Cloudflare's view."""

    def __init__(self, sync="off"):
        self.cfg = {
            "a": cfg(SYNC_MODE=sync),
            "b": cfg(NODE_NAME="crm-b", PEER_NAME="crm-a", SYNC_MODE=sync),
        }
        self.pg = {"a": "primary", "b": "standby"}
        self.tl = {"a": 1, "b": 1}
        self.lsn = {"a": 1000, "b": 1000}
        self.state = {"a": initial_state(), "b": initial_state()}
        self.link = True
        self.public = {"a": True, "b": True}
        self.cf_api = True
        self.cf_down_ticks = {"a": 0, "b": 0}
        self.sync = {"a": "", "b": ""}
        self.log = []

    def peer(self, n):
        return "b" if n == "a" else "a"

    def streaming(self, n):
        p = self.peer(n)
        pair = {self.pg[n], self.pg[p]}
        return self.link and pair == {"primary", "standby"} and self.tl[n] == self.tl[p]

    def cf_truth(self, n):
        # The monitor: 200 only from a primary reachable from the internet; 2 failures to go down.
        ok = self.public[n] and self.pg[n] == "primary"
        self.cf_down_ticks[n] = 0 if ok else self.cf_down_ticks[n] + 1
        return "healthy" if ok or self.cf_down_ticks[n] < 2 * 4 else "unhealthy"  # 2 x 60 s at 15 s ticks

    def tick(self, t, rng=None):
        truth = {n: self.cf_truth(n) for n in ("a", "b")}
        for n in ("a", "b"):
            if self.pg[n] == "primary":
                self.lsn[n] += 100
        for n in ("a", "b"):
            if self.streaming(n) and self.pg[n] == "standby":
                self.lsn[n] = self.lsn[self.peer(n)]
        for n in ("a", "b"):
            p = self.peer(n)

            def seen(x):
                if not self.cf_api or not self.public[n]:
                    return "unknown"
                if rng is not None and rng.random() < 0.1:
                    return "unknown"
                return truth[x]

            o = Obs(
                self_pg=self.pg[n], self_streaming=self.streaming(n), self_lsn=self.lsn[n],
                peer_pg=(self.pg[p] if self.pg[p] != "down" else "unreachable") if self.link else "unreachable",
                peer_lsn=self.lsn[p] if self.link and self.pg[p] != "down" else None,
                cf_self=seen(n), cf_peer=seen(p), sync_names=self.sync[n],
            )
            self.state[n], actions = decide(self.state[n], o, t, self.cfg[n])
            for a in actions:
                self.apply(n, a, t)
        assert not (self.pg["a"] == "primary" and self.pg["b"] == "primary"), f"two writers at t={t}: {self.log[-6:]}"

    def apply(self, n, a, t):
        self.log.append((t, n, a))
        p = self.peer(n)
        if a[0] == "fence":
            self.pg[n] = "down"
        elif a[0] == "promote":
            assert self.pg[n] == "standby"
            self.pg[n] = "primary"
            self.tl[n] = max(self.tl.values()) + 1
        elif a[0] == "start_standby":
            if self.pg[n] == "down":
                self.pg[n] = "standby"
        elif a[0] == "rejoin":
            if self.link and self.pg[p] == "primary":
                self.pg[n] = "standby"
                self.tl[n] = self.tl[p]
                self.lsn[n] = self.lsn[p]
        elif a[0] == "set_sync":
            self.sync[n] = a[1]

    def run(self, until, start=0, rng=None):
        t = start
        while t <= until:
            self.tick(t, rng)
            t += TICK
        return t


def test_world_node_a_dies_b_takes_over_and_a_rejoins_as_standby():
    w = World()
    w.run(300)
    assert w.pg == {"a": "primary", "b": "standby"}
    w.public["a"] = False
    w.link = False
    w.run(1500, start=315)
    assert w.pg["b"] == "primary"
    assert w.pg["a"] == "down"
    w.public["a"] = True
    w.link = True
    w.run(1800, start=1515)
    assert w.pg == {"a": "standby", "b": "primary"}
    assert w.tl["a"] == w.tl["b"]


def test_world_link_cut_alone_changes_nothing():
    w = World()
    w.link = False
    w.run(7200)
    assert w.pg == {"a": "primary", "b": "standby"}


def test_world_cloudflare_api_down_never_promotes():
    w = World()
    w.cf_api = False
    w.run(7200)
    assert w.pg["b"] == "standby"


def test_world_cloudflare_api_and_link_down_fence_then_recover_to_one_writer():
    w = World()
    w.cf_api = False
    w.link = False
    w.run(3600)
    assert w.pg["a"] == "down" and w.pg["b"] == "standby"
    w.cf_api = True
    w.link = True
    w.run(5400, start=3615)
    assert sorted(w.pg.values()) == ["primary", "standby"]


def test_world_app_sick_on_a_moves_the_writer_to_b():
    w = World()
    w.public["a"] = False  # Cloudflare cannot get a 200 from A; the link stays up
    w.run(3600)
    assert w.pg["b"] == "primary"
    assert w.pg["a"] == "standby"  # rejoined


def test_world_both_reboot_one_writer_comes_back():
    w = World()
    w.run(300)
    w.pg = {"a": "down", "b": "down"}
    w.run(900, start=315)
    assert w.pg == {"a": "primary", "b": "standby"}


def test_world_sync_names_track_the_stream():
    w = World(sync="remote_write")
    w.run(60)
    assert w.sync["a"] == "crm-b"
    w.link = False
    w.run(90, start=75)
    assert w.sync["a"] == ""


@pytest.mark.parametrize("seed", range(40))
def test_world_random_faults_never_two_writers(seed):
    rng = random.Random(seed)
    w = World(sync=rng.choice(["off", "remote_write"]))
    t = 0
    for _ in range(25):
        w.link = rng.random() < 0.6
        w.public = {"a": rng.random() < 0.7, "b": rng.random() < 0.7}
        w.cf_api = rng.random() < 0.85
        if rng.random() < 0.1:
            n = rng.choice("ab")
            w.pg[n] = "down"  # crash or reboot (the controller state survives on disk)
        t = w.run(t + rng.choice([60, 300, 900, 1800]), start=t, rng=rng)


def test_obs_is_a_frozen_value():
    o = obs()
    assert replace(o, self_lsn=5).self_lsn == 5

"""WhatsApp round-trip latency: turn pairing, percentiles, breach detection.

Measures **user presses send -> our reply is accepted by Respond**, against a p99 target.

Three deliberate narrowings, each of which is load-bearing:

1. **One clock.** Both ends read `respond_ts`, the authoritative Respond-side timestamp.
   `sent_at` is whatever n8n supplied and is not trustworthy - on production rows an
   outgoing `sent_at` can precede the incoming message it answers, which would yield
   negative latency. Rows whose `respond_ts` is not yet resolved are omitted, never
   approximated.

2. **The clock stops at *sent*.** Delivery to the handset is the recipient's business: a
   phone that is switched off would otherwise own the p99 tail with nothing an engineer
   could fix. Delivery is tracked (`count_undelivered`) and alerted on separately.

3. **Pairing is by `turn_id`** (the n8n `$execution.id`), never by proximity in time.
   Proactive sends carry no turn and leave the denominator entirely rather than being
   paired by guesswork.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.chat_history import ChatHistory

# Below this many paired turns, a window-level percentile is noise rather than signal,
# so fleet-level breach alerting stays quiet. The hard ceiling (`get_stalled_turns`)
# has no such floor - one catastrophic turn should alert on its own.
DEFAULT_MIN_SAMPLE = 30

# Delivery states that mean "Respond accepted it", i.e. our part is done.
_SENT_STATES = ("sent", "delivered", "read")


@dataclass(frozen=True)
class Turn:
    turn_id: str
    contact_id: str
    started_at: datetime          # respond_ts of the incoming message
    replied_at: datetime          # respond_ts of the FIRST outgoing reply
    latency_seconds: float
    webhook_lag_seconds: Optional[float]  # ingest_at - respond_ts on the incoming


@dataclass(frozen=True)
class UnansweredTurn:
    turn_id: str
    contact_id: str
    started_at: datetime
    waiting_seconds: float


@dataclass(frozen=True)
class LatencyStats:
    count: int
    p50: Optional[float]
    p95: Optional[float]
    p99: Optional[float]
    max: Optional[float]


@dataclass(frozen=True)
class BreachVerdict:
    breached: bool
    reason: Optional[str]


def _percentile(values: list[float], q: float) -> Optional[float]:
    """Nearest-rank percentile. Deterministic and dependency-free."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _rows_with_turns(db: Session, since: datetime) -> list[ChatHistory]:
    return (
        db.query(ChatHistory)
        .filter(
            ChatHistory.turn_id.isnot(None),
            ChatHistory.respond_ts.isnot(None),   # unresolved rows have no honest clock
            ChatHistory.respond_ts >= since,
        )
        .order_by(ChatHistory.respond_ts.asc(), ChatHistory.id.asc())
        .all()
    )


def get_turns(db: Session, since: datetime) -> list[Turn]:
    """Complete turns in the window, one per turn_id, worst latency last."""
    incoming: dict[str, ChatHistory] = {}
    first_reply: dict[str, ChatHistory] = {}

    for row in _rows_with_turns(db, since):
        key = str(row.turn_id)
        if row.type == "incoming":
            # Earliest incoming anchors the turn; rows arrive ordered by respond_ts.
            incoming.setdefault(key, row)
        else:
            # First reply only - a multi-part answer is judged on when it *starts*,
            # which is what the user perceives as responsiveness.
            first_reply.setdefault(key, row)

    turns: list[Turn] = []
    for key, start in incoming.items():
        reply = first_reply.get(key)
        if reply is None:
            continue
        latency = (reply.respond_ts - start.respond_ts).total_seconds()
        lag = (
            (start.ingest_at - start.respond_ts).total_seconds()
            if start.ingest_at is not None
            else None
        )
        turns.append(
            Turn(
                turn_id=key,
                contact_id=str(start.contact_id),
                started_at=start.respond_ts,
                replied_at=reply.respond_ts,
                latency_seconds=latency,
                webhook_lag_seconds=lag,
            )
        )

    turns.sort(key=lambda t: t.latency_seconds)
    return turns


def get_unanswered_turns(
    db: Session,
    now: datetime,
    older_than_seconds: int = 300,
) -> list[UnansweredTurn]:
    """Incoming messages with no reply after `older_than_seconds`.

    This is the shape a dropped webhook or a wedged workflow takes: the turn never
    completes, so it never appears in the latency distribution at all. Counting only
    completed turns would report a healthy p99 through exactly this outage.
    """
    cutoff = now - timedelta(seconds=older_than_seconds)
    rows = _rows_with_turns(db, since=now - timedelta(days=1))

    incoming: dict[str, ChatHistory] = {}
    replied: set[str] = set()
    for row in rows:
        key = str(row.turn_id)
        if row.type == "incoming":
            incoming.setdefault(key, row)
        else:
            replied.add(key)

    out: list[UnansweredTurn] = []
    for key, start in incoming.items():
        if key in replied or start.respond_ts > cutoff:
            continue
        out.append(
            UnansweredTurn(
                turn_id=key,
                contact_id=str(start.contact_id),
                started_at=start.respond_ts,
                waiting_seconds=(now - start.respond_ts).total_seconds(),
            )
        )
    out.sort(key=lambda u: u.waiting_seconds, reverse=True)
    return out


def get_stalled_turns(
    db: Session,
    since: datetime,
    ceiling_seconds: float,
) -> list[Turn]:
    """Individual turns past the hard ceiling.

    No minimum sample size: one turn taking 10x the target is actionable on its own,
    and at high volume it would never move a windowed percentile.
    """
    return [t for t in get_turns(db, since) if t.latency_seconds > ceiling_seconds]


def compute_latency_stats_from_values(values: list[float]) -> LatencyStats:
    """Stats from a bare list - the pure core, so percentile behaviour is
    testable without constructing turns in a database."""
    if not values:
        return LatencyStats(count=0, p50=None, p95=None, p99=None, max=None)
    return LatencyStats(
        count=len(values),
        p50=_percentile(values, 0.50),
        p95=_percentile(values, 0.95),
        p99=_percentile(values, 0.99),
        max=max(values),
    )


def compute_latency_stats(db: Session, since: datetime) -> LatencyStats:
    return compute_latency_stats_from_values(
        [t.latency_seconds for t in get_turns(db, since)]
    )


# Percentiles the watchdog can alert on. Restricted to the ones that are
# meaningful to state as a policy - an arbitrary quantile would also make the
# alert text ("p87 …") unreadable.
_ALERT_PERCENTILES = {50: "p50", 95: "p95", 99: "p99"}
DEFAULT_ALERT_PERCENTILE = 99


def evaluate_breach(
    stats: LatencyStats,
    target_seconds: float,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    percentile: int = DEFAULT_ALERT_PERCENTILE,
) -> BreachVerdict:
    """Fleet-level verdict. Quiet on an empty or too-small window.

    `percentile` selects which computed percentile is held to `target_seconds`.
    An unrecognised value falls back to p99 rather than disabling the check - a
    bad settings value must not silently switch alerting off.
    """
    label = _ALERT_PERCENTILES.get(int(percentile or 0), "p99")
    observed = getattr(stats, label)

    if stats.count == 0 or observed is None:
        return BreachVerdict(False, None)
    if stats.count < min_sample:
        return BreachVerdict(False, None)
    if observed > target_seconds:
        return BreachVerdict(
            True,
            f"{label} {observed:.1f}s over {stats.count} turns "
            f"exceeds target {target_seconds:.0f}s",
        )
    return BreachVerdict(False, None)


def count_undelivered(
    db: Session,
    now: datetime,
    older_than_seconds: int = 900,
) -> int:
    """Outgoing messages Respond accepted but never confirmed delivered.

    Channel health, not performance - reported next to the SLA, never inside it.
    """
    cutoff = now - timedelta(seconds=older_than_seconds)
    return (
        db.query(ChatHistory)
        .filter(
            ChatHistory.type == "outgoing",
            ChatHistory.respond_ts.isnot(None),
            ChatHistory.respond_ts <= cutoff,
            ChatHistory.delivery_status == "sent",  # accepted, never progressed
        )
        .count()
    )

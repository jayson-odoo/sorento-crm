"""Ordering one contact's turns, and re-injecting a failed one (AC-705, AC-709, AC-710).

Two jobs, one module, because they are the same subject seen twice: WHICH turn for this
contact runs next. The ordering half is the S7 replacement for n8n's `sorento-dispatcher`,
which popped one contact per second and therefore served a 50-dealer burst over 50 seconds
no matter how fast the CRM was. The re-inject half puts an operator's Retry back through
the front door so it takes the same ordering everything else takes.

R4: there is no automatic retry anywhere. An operator presses Retry on the trace screen,
and what that does is put the customer's ORIGINAL message back through the front door -
n8n's inject webhook, the same one the failover poller uses - so the turn re-enters with
the same ordering, the same lanes and the same sending path a live message gets.

**The CRM does not send, and does not re-run the turn in place.** Both would be the same
mistake in different clothes: the engine answering from a click would bypass n8n's egress
containment (D9), and a fresh in-process run would write a reply nobody delivered. What
happens instead is one HTTP POST of bytes the CRM already has, and then the turn arrives
back the ordinary way, as its own row.

**Unset locally on purpose.** With no `CHATBOT_RETRY_INGRESS_URL` the caller answers 409
`retry_unavailable` and nothing is posted. A dev machine that silently injected into
production n8n would answer a real customer from a developer's click, and the failure
would look like a bug in the customer's conversation rather than in somebody's `.env`.

From S7 the URL moves to the thin spine's own webhook. Nothing else here changes: the
body is the respond.io webhook body either way, which is exactly why this seam is one
function and one env var rather than a transport abstraction.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from redis import exceptions as redis_exceptions

from app.config import settings
from app.services.queue_service import REDIS_SOCKET_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Per-contact ordering (AC-709, AC-710, H30, H31)
#
# Three keys per contact, and the third one is the interesting one:
#
#   chatbot:seq:{contact}      the ticket counter. INCR on arrival; a turn's ticket is
#                              its place in the queue for THIS contact only.
#   chatbot:done:{contact}     the last ticket that finished. Absent means zero.
#   chatbot:running:{contact}  present only while a ticket is actually being worked.
#
# `running` exists so a waiter can tell "my predecessor is slow" from "my predecessor is
# dead". The dead case is the one that matters: a process killed mid-turn never advances
# `done`, and without a repair every later message from that contact would wait out the
# full queue timeout and fail - one crashed turn silently breaking a conversation for as
# long as the customer keeps typing. So `mark_done` DELETES the key rather than letting it
# expire, and a waiter that sees it absent for `STALL_GRACE_SECONDS` repairs the counter
# and goes.
#
# The key is set by `contact_ticket`, in the SAME pipeline as the INCR, and not after the
# wait. A ticket that exists but whose holder has not reached `mark_running` yet would
# otherwise be invisible, and a waiter whose own poll happened to be slow could call a
# live predecessor dead and run beside it - the one failure per-contact ordering exists to
# prevent. "A ticket exists" and "somebody is alive holding it" become one write.
#
# Every write to `done` is MONOTONE (`_advance_done`, a compare-and-set in Lua). Two
# writers reach it - a finishing turn and a repairing waiter - and a plain SET from either
# could move the counter BACKWARDS, which strands the next ticket behind a number that has
# already passed. Nothing here may lower it.
#
# Redis, not Postgres advisory locks: the wait is a poll of one integer, it must not hold a
# database connection while it waits (the capacity rule), and redis is already the queue
# substrate this process talks to.
# --------------------------------------------------------------------------- #

# The counter is per conversation and a conversation goes quiet. An hour after the last
# message the keys are worthless, and a fresh contact starting again at ticket 1 is
# correct - nothing is waiting on the old numbers.
TICKET_TTL_SECONDS = 3600

# How long the `running` key survives without anyone clearing it. Far longer than a turn
# (the whole turn budget is tens of seconds), because a key that lapsed mid-turn would
# invite a repair while its holder is still working - two turns for one contact at once,
# the exact thing this is for.
#
# It is therefore LONGER than the queue budget, so a process killed with the key set does
# leave the contact looking busy. What bounds that is not this number: the waiter gives up
# after `chatbot_queue_wait_seconds` and releases its own ticket on the way out (see
# `wait_for_turn`), so the stale key costs one turn, not five minutes of them.
RUNNING_TTL_SECONDS = 300

# The waiter polls; it does not subscribe. One integer read every 200 ms for at most the
# queue-wait window is a handful of cheap reads, and a pub/sub channel per contact would be
# a second mechanism to keep alive for no measured gain.
POLL_INTERVAL_SECONDS = 0.2

# How long `running` may be ABSENT before a waiter decides the predecessor died and repairs
# the counter.
#
# It has to clear the REDIS SOCKET TIMEOUT (`queue_service.REDIS_SOCKET_TIMEOUT_SECONDS`,
# 10 s), because the probe that reads the key is itself a redis round trip on that
# connection: with a two-second grace, one slow redis call is enough to make a live
# predecessor look dead, and the repair would then let two turns for one contact run at
# once. Twelve seconds is that timeout plus a poll, and still a quarter of the 45 s queue
# budget, so a genuinely dead predecessor is repaired long before the waiter gives up.
STALL_GRACE_SECONDS = float(REDIS_SOCKET_TIMEOUT_SECONDS) + 2.0


class QueueWait(RuntimeError):
    """The wait for this contact's turn exceeded the budget. The turn fails at `queued`."""


# What "redis is not answering" looks like from here. The engine catches these and runs the
# turn UNORDERED rather than failing it: ordering is an improvement on the reply's order,
# and a redis blip costs the chatbot nothing on this path today. Trading "answered out of
# order" for "not answered at all" would make the ordering flag a new way for the whole
# chatbot to go down. `OSError` rides along because a socket error can reach the caller
# before redis-py has wrapped it.
ORDERING_ERRORS: tuple[type[BaseException], ...] = (redis_exceptions.RedisError, OSError)


def seq_key(contact: str) -> str:
    return f"chatbot:seq:{contact}"


def done_key(contact: str) -> str:
    return f"chatbot:done:{contact}"


def running_key(contact: str) -> str:
    return f"chatbot:running:{contact}"


def _as_int(value: Any) -> int:
    """A redis value as an int. Absent is 0, and so is anything unreadable.

    Both client shapes reach this: the engine's connection decodes nothing
    (`queue_service.redis_conn`, `decode_responses=False`), a test's client decodes
    everything. A counter that cannot be read is treated as "nothing finished yet", which
    makes a waiter wait rather than run out of turn.
    """
    if value is None:
        return 0
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# A compare-and-set, because `done` has two writers and neither may lower it. Written in
# Lua rather than WATCH/MULTI so it is one round trip and cannot be interleaved: redis runs
# the whole script before it serves anything else.
_ADVANCE_DONE_LUA = """
local current = tonumber(redis.call('GET', KEYS[1])) or 0
local target = tonumber(ARGV[1])
if current < target then
  redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
  return target
end
return current
"""


def _advance_done(redis: Any, contact: str, ticket: int) -> None:
    """Move `done` UP to `ticket`, never down. Both writers go through here."""
    redis.eval(
        _ADVANCE_DONE_LUA, 1, done_key(contact), int(ticket), int(TICKET_TTL_SECONDS)
    )


def contact_ticket(redis: Any, contact: str) -> int:
    """This turn's place in the queue for this contact. Monotonic per contact.

    The liveness key is set HERE, in the same pipeline as the INCR: the moment a ticket
    exists, its holder is visibly alive. Doing it after the wait instead leaves a window -
    short, but a waiter's own probe is a network call - in which a live predecessor reads
    as a dead one and gets jumped.
    """
    key = seq_key(contact)
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, TICKET_TTL_SECONDS)
    pipe.set(running_key(contact), 1, ex=RUNNING_TTL_SECONDS)
    ticket = int(pipe.execute()[0])
    return ticket


def mark_running(redis: Any, contact: str, ticket: int) -> None:
    """Say this ticket is being worked, so a waiter does not mistake it for a dead one.

    Still needed after the wait even though `contact_ticket` already set the key: the
    predecessor's `mark_done` DELETED it on its way out, and the successor has to put it
    back before the next waiter's grace window runs out.
    """
    redis.set(running_key(contact), int(ticket), ex=RUNNING_TTL_SECONDS)


def mark_done(redis: Any, contact: str, ticket: int) -> None:
    """Release the next waiter. Called from a `finally`, so a FAILED turn releases too.

    Monotone (`_advance_done`): a turn that finishes out of order - the one case a
    spurious repair can create - must not pull the counter back to its own number and
    strand every ticket the repair already let through.

    Deleting `running` rather than letting it lapse is what makes its absence a signal
    (see the block comment above).
    """
    _advance_done(redis, contact, ticket)
    redis.delete(running_key(contact))


def wait_for_turn(redis: Any, contact: str, ticket: int, *, timeout_s: float) -> None:
    """Block until every earlier ticket for this contact has finished.

    Returns as soon as `done >= ticket - 1`, repairs a stalled counter after
    `STALL_GRACE_SECONDS` with no `running` key, and raises `QueueWait` if neither happens
    inside `timeout_s`. The caller records that as a turn failed at stage `queued`; it
    never hangs the request past the budget.

    **A `QueueWait` still advances the counter**, because the engine calls `mark_done` in
    a `finally` that covers this wait. That is what bounds the other death case: a process
    killed with its `running` key still SET stays "alive" for the key's whole TTL, so no
    repair can fire and every later message from that contact would wait out the budget
    and fail - for five minutes. Giving up now costs exactly one turn instead, and the
    turn that gave up produces no reply, so letting its successors through reorders
    nothing that was ever going to be said.
    """
    target = int(ticket) - 1
    if target <= 0 and _as_int(redis.get(done_key(contact))) >= target:
        return

    deadline = time.monotonic() + max(0.0, float(timeout_s))
    absent_since: float | None = None

    while True:
        if _as_int(redis.get(done_key(contact))) >= target:
            return

        now = time.monotonic()
        if redis.exists(running_key(contact)):
            # Somebody is genuinely working. Reset the death timer: a predecessor that
            # takes 30 s is slow, not dead, and jumping it would answer out of order.
            absent_since = None
        elif absent_since is None:
            absent_since = now
        elif now - absent_since > STALL_GRACE_SECONDS:
            logger.warning(
                "chatbot ordering: repairing stalled counter for %s (ticket %s, done -> %s)",
                contact,
                ticket,
                target,
            )
            _advance_done(redis, contact, target)
            return

        if time.monotonic() >= deadline:
            raise QueueWait(
                f"waited {timeout_s}s for ticket {target} of contact {contact} to finish"
            )
        time.sleep(POLL_INTERVAL_SECONDS)


# --------------------------------------------------------------------------- #
# Re-injecting a failed turn (AC-705)
# --------------------------------------------------------------------------- #

# n8n's HTTP node waits the whole turn, so this is generous: the call being answered
# means "n8n accepted the message", not "the turn finished".
REINJECT_TIMEOUT_SECONDS = 10.0

RETRY_KEY_HEADER = "X-Chatbot-Retry-Key"


class RetryUnavailable(RuntimeError):
    """No ingress is configured, so nothing was posted. The caller answers 409."""


class ReinjectFailed(RuntimeError):
    """The ingress answered non-2xx. The caller answers 502 and leaves the row alone."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"ingress returned {status_code}: {body}")
        self.status_code = status_code
        self.body = body


def ingress_url() -> str | None:
    """The configured inject webhook, or None when retry is not wired here."""
    url = (settings.chatbot_retry_ingress_url or "").strip()
    return url or None


def retry_available() -> bool:
    """Read by the endpoint so the UI can disable Retry rather than offer a 409."""
    return ingress_url() is not None


def reinject_envelope(row: Any) -> None:
    """Re-post the turn's ORIGINAL respond.io webhook body to the ingress.

    `row` is a `ChatbotTurn`. What goes on the wire is `envelope.message` exactly as it
    was stored - not a rebuilt envelope. n8n's webhook is the producer's contract and it
    expects a respond.io body; handing it anything the CRM composed would make the retry
    path a second, untested shape of the thing being retried.

    Raises `RetryUnavailable` (nothing sent) or `ReinjectFailed` (ingress refused).
    """
    import httpx

    url = ingress_url()
    if url is None:
        raise RetryUnavailable(
            "no retry ingress is configured for this environment "
            "(CHATBOT_RETRY_INGRESS_URL is unset)"
        )

    envelope = row.envelope if isinstance(row.envelope, dict) else {}
    body = envelope.get("message")
    if not isinstance(body, dict) or not body:
        raise RetryUnavailable(
            "this turn did not store the original message, so there is nothing to re-post"
        )

    headers = {"Content-Type": "application/json"}
    key = (settings.chatbot_retry_ingress_key or "").strip()
    if key:
        headers[RETRY_KEY_HEADER] = key

    try:
        response = httpx.post(
            url, json=body, headers=headers, timeout=REINJECT_TIMEOUT_SECONDS
        )
    except Exception as exc:  # noqa: BLE001 - a transport failure is the ingress refusing
        logger.warning("chatbot retry re-inject failed to reach the ingress: %s", exc)
        raise ReinjectFailed(0, str(exc)) from exc

    if response.status_code >= 300:
        logger.warning(
            "chatbot retry re-inject rejected: %s %s", response.status_code, response.text[:300]
        )
        raise ReinjectFailed(response.status_code, response.text[:500])

    logger.info(
        "chatbot retry re-injected turn %s for contact %s", row.id, row.contact_respond_id
    )

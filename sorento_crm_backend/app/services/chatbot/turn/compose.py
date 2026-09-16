# Composers return data first, text second (PLAN-chatbot-turn-rearch.md "Fetch and
# compose", AC-1531): `compose(envelopes, state, policy, ctx) -> Answer`, `Answer =
# {sections, question, offer, canned, files, actions, text}`. The #930 grammar
# (contract 102 to 105) renders `text` FROM the sections here - `figures` keeps
# today's per-row shape (`{"fields": [{"label", "value"}], ...}`, the same shape
# `lanes/business/fetch.py::output_structurer` already produces), so a domain's own
# composer (kept, unchanged per the plan) has somewhere familiar to write into.
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from app.services.chatbot.turn.fetch import envelope_missed
from app.services.chatbot.turn.narrow import ledger_family_key, ledger_family_label
from app.services.chatbot.turn.pending import ask as pending_ask, is_roster
from app.services.chatbot.turn.policy import Policy
from app.services.chatbot.turn.state import State

_ATTACHED_SENTENCE = "I have attached the file(s) below."


@dataclass
class Section:
    domain: str
    entities: list[Any] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    miss: list[Any] = field(default_factory=list)


@dataclass
class Offer:
    teams: list[str] = field(default_factory=list)


@dataclass
class Answer:
    sections: list[Section] = field(default_factory=list)
    question: Any = None
    offer: Offer | None = None
    canned: list[Any] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""


def _row_key(fig: dict[str, Any]) -> tuple:
    return tuple((f.get("label"), f.get("value")) for f in fig.get("fields") or [])


def _render_row(n: int, fig: dict[str, Any]) -> str:
    lines: list[str] = []
    for i, f in enumerate(fig.get("fields") or []):
        prefix = f"{n}. " if i == 0 else ""
        lines.append(f"{prefix}*{f.get('label')}:* {f.get('value')}")
    return "\n".join(lines)


def _file_key(f: dict[str, Any]) -> Any:
    return f.get("url") or f.get("id") or f.get("filename")


def _team_pick_question(missed_domains: list[str], policy: Policy):
    """Team pick over the missed domains (contract 106-113, 127; AC-1533). A single
    missed team is yes/no over that one team; two or more become a numbered pick plus
    a "No it's okay" hold option (contract 43).

    `Pending.team` stays a single `str | None` (S2): set when there is exactly one
    team, else None until the pick resolves - each option carries ITS OWN team under
    `payload.team` (captain ruling, 16 Sep 2026).
    """
    teams: list[tuple[str, str]] = []
    seen: set[str] = set()
    for domain in missed_domains:
        row = policy.domain(domain) if policy else None
        team = row.escalation_team_code if row else None
        if not team or team in seen:
            continue
        seen.add(team)
        teams.append((team, row.label if row else domain))

    if not teams:
        return None

    if len(teams) == 1:
        team, label = teams[0]
        options = [{"position": 1, "label": label, "entity_type": "team", "payload": {"team": team}}]
        return pending_ask("team_pick", options, team=team, expects="yes_no")

    options = [
        {"position": i + 1, "label": label, "entity_type": "team", "payload": {"team": team}}
        for i, (team, label) in enumerate(teams)
    ]
    options.append(
        {
            "position": len(options) + 1,
            "label": "No it's okay",
            "entity_type": "team",
            # Contract 43, the offer hold: picking this option is a DECLINE, and it says
            # so in its own payload rather than being inferred from a null team - a
            # `company_pick` option carries no team either, and "the customer said no"
            # must not be a thing the reader works out from a missing field.
            "payload": {"team": None, "hold": True},
        }
    )
    return pending_ask("team_pick", options, team=None, expects="pick")


def _lane_question(envelopes: list[dict[str, Any]], turn_no: int | None = None):
    """The question a LANE asked, as the turn's pending (contract 38, 39).

    A fetch can come back with a question instead of an answer - the outstanding report
    asks which document before it searches, and offers its detail lists after it has -
    and it hands that over on `fetch.outstanding_ask` rather than composing a reply the
    composer would have to parse back. The options are the lane's own rows
    (`{idx, label, value}`), renumbered into the roster shape the tail stores and the
    parser is shown, and the filters it resolved ride on the payload so the turn that
    answers has the subject the question was asked about.

    The FIRST lane to ask wins, because a session holds one open question at a time.
    """
    for env in envelopes:
        ask = env.get("lane_ask")
        if not isinstance(ask, dict) or not ask.get("kind"):
            continue
        rows = [r for r in (ask.get("last_result_set") or []) if isinstance(r, dict)]
        options = [
            {
                "position": int(row.get("idx") or i + 1),
                "label": row.get("label"),
                "entity_type": str(ask.get("kind")),
                "payload": {"value": row.get("value")},
            }
            for i, row in enumerate(rows)
        ]
        if not options:
            continue
        return pending_ask(
            str(ask.get("kind")),
            options,
            expects="pick",
            asked_at_turn=turn_no,
            payload={
                "domain": env.get("domain"),
                "filters": dict(ask.get("filters") or {}),
            },
        )
    return None


def _header_subjects(entities: list[Any]) -> list[str]:
    """Every subject the answer is FOR, each named once.

    Owner ruling, hand pass 3 row 2 (turn 463413b0): "All" over a customer roster fetched
    fifteen ledgers, correctly, and the header then said one trading name once per ledger
    of it - "CHIN CHUN HARDWARE SDN BHD - [A/C I]" six times over, "JIMMY - I, JIMMY - I".
    Ledgers of one trading name are ONE customer, which is the rule `narrow` already
    groups a roster by, so the header groups by the same one and prints the family's own
    name rather than any one ledger's.

    A code with no family (every product code) keys on itself, so the only thing this
    collapses there is a genuine repeat.
    """
    out: list[str] = []
    seen: set[str] = set()
    for value in entities:
        text = str(value).strip()
        if not text:
            continue
        key = ledger_family_key(text) or text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(ledger_family_label(text))
    return out


def compose(envelopes: list[dict[str, Any]], state: State, policy: Policy, ctx: Any) -> Answer:
    sections: list[Section] = []
    seen_rows: set[tuple] = set()
    text_parts: list[str] = []
    missed_domains: list[str] = []
    files: list[dict[str, Any]] = []
    seen_file_keys: set[Any] = set()

    for env in envelopes:
        domain = env.get("domain")
        row = policy.domain(domain) if policy else None
        entities = env.get("entities") or []
        figures = env.get("figures") or []
        miss = env.get("miss") or []
        env_files = env.get("files") or []

        sections.append(Section(domain=domain, entities=entities, figures=figures, files=env_files, miss=miss))

        rows_text: list[str] = []
        n = 0
        for fig in figures:
            key = _row_key(fig)
            if key in seen_rows:
                continue
            seen_rows.add(key)
            n += 1
            rows_text.append(_render_row(n, fig))

        # ONE miss rule, shared with the ladder that climbs on it
        # (`turn/fetch.py::envelope_missed`): two copies of "did this domain answer
        # nothing" would let the rung walk and the escalate offer disagree about the
        # same envelope.
        if envelope_missed(env):
            missed_domains.append(domain)

        label = row.label if row else domain
        codes = ", ".join(_header_subjects(entities))
        # A counted-set answer (AC-1316/AC-1317, "10 taps have certificates. Showing
        # 5.") carries its OWN header, computed off the qualifying total and the
        # class word rather than the domain label - it wins over the generic
        # `*{label}* for {codes}:` line whenever the fetch supplied one, rows or not.
        header_override = env.get("header_override")
        if isinstance(header_override, str) and header_override.strip():
            header = header_override.strip()
        else:
            header = f"*{label}* for {codes}:" if codes else f"*{label}*:"
        # A tool that renders its own answer - a report, a refusal, a miss suggestion -
        # hands it over as `lane_text` and the section prints THAT; rows go through the
        # grammar above (contract 102). One or the other, never both.
        lane_words = env.get("lane_text")
        if rows_text:
            block = header + "\n" + "\n\n".join(rows_text)
        elif (env.get("denied") or env.get("own_header")) and isinstance(lane_words, str) and lane_words.strip():
            # Contract 7. A refusal is the WHOLE section and carries no header: naming
            # the domain above "Sorry, you are not allowed to access purchase cost"
            # would print the very thing the sentence is refusing to discuss. Checked
            # before the generic `lane_text` branch below for that reason.
            #
            # AC-1139 puts the outstanding report on the same footing: it opens with its
            # OWN four-line scope header (`Product:` / `Customer:` / `Location:` /
            # `Order date:`), so the generic `*orders* for SRTWT7445:` line above it
            # states the search scope twice, in two different grammars, over one answer.
            block = lane_words.strip()
        elif isinstance(lane_words, str) and lane_words.strip():
            # The header still names the domain: one section per domain is the grammar
            # (contract 122), and a fan-out whose second leg found nothing must still say
            # WHICH leg that was.
            block = header + "\n" + lane_words.strip()
        elif env.get("denied"):
            block = f"*{label}*: this is not enabled for your account."
        else:
            block = header
        # The window the fetch ran with, stated under the header it belongs to (browser
        # pass 6 item 4). Never on a section that states its own scope - the outstanding
        # report and the refusal both do, and the report's own four-line block already
        # carries this exact line (`own_header`), so printing it here too would say the
        # same dates twice in one answer.
        date_line = env.get("date_line")
        if (
            isinstance(date_line, str)
            and date_line.strip()
            and not env.get("own_header")
            and not env.get("denied")
        ):
            head, sep, rest = block.partition("\n")
            block = head + "\n" + date_line.strip() + (sep + rest if sep else "")
        # AC-922, "nothing on any rung": the primary domain missed AND every domain on
        # its ladder missed too. Named once, here, rather than as one empty header per
        # rung - the customer asked about a product, not about three domains.
        rungs_tried = [r for r in (env.get("rungs_tried") or []) if isinstance(r, str)]
        if rungs_tried:
            names = [
                (policy.domain(r).label if (policy and policy.domain(r)) else r)
                for r in rungs_tried
            ]
            block = block + "\n" + f"Nothing on {_join_words(names)} either."
        text_parts.append(block)

        for f in env_files:
            key = _file_key(f)
            if key in seen_file_keys:
                continue
            seen_file_keys.add(key)
            files.append(f)

    text = "\n\n".join(text_parts)

    offer = None
    # ONE open question per turn, and when a lane asked one it is the lane's: a domain
    # that has just asked "which document?" or offered its detail lists is waiting for
    # THAT answer, and an escalate offer over the top of it would leave the customer
    # looking at two numbered lists for one reply - and store the wrong roster for the
    # number they send back.
    question = _lane_question(envelopes, getattr(state, "turn_no", None))
    if question is None and envelopes and missed_domains and len(missed_domains) == len(envelopes):
        teams: list[str] = []
        for domain in missed_domains:
            row = policy.domain(domain) if policy else None
            team = row.escalation_team_code if row else None
            if team and team not in teams:
                teams.append(team)
        if teams:
            offer = Offer(teams=teams)
            text += "\n\nWould you like me to escalate?"
            carried = getattr(state, "pending", None)
            if carried is not None and is_roster(carried.kind):
                # Owner hand pass 2, item 8 (turns 29605e65 miss, then 586746d3 "5" and
                # a253e14f "3"): the escalate offer REPLACED the sticky roster the miss
                # was about, so the next number resolved against a team picker and the
                # customer got the offer printed back at them twice. A roster survives
                # its own pick (contract 36) and it survives a miss too - the offer is a
                # SENTENCE appended under the answer, not a second question. The team it
                # would escalate to rides on the roster, so a "yes" over this state still
                # reaches the right team.
                question = replace(
                    carried,
                    team=carried.team or teams[0],
                    payload={**carried.payload, "escalate_offered": True},
                )
            else:
                question = _team_pick_question(missed_domains, policy)

    actions: list[dict[str, Any]] = []
    if files:
        actions = [
            {"kind": "send_file", "url": f.get("url"), "filename": f.get("filename")} for f in files
        ]
        text += "\n\n" + _ATTACHED_SENTENCE

    return Answer(
        sections=sections, question=question, offer=offer, canned=[], files=files, actions=actions, text=text
    )


# The sentence each pending kind opens with. One wording per question, in one place, so
# the ask a customer reads and the pending the tail stores can never describe different
# questions (contract 29, 37, 50).
_ASK_HEADERS: dict[str, str] = {
    "product_pick": "Which product do you mean?",
    "customer_pick": "Which customer do you mean?",
    "tier_pick": "Which price tier applies to you?",
    "team_pick": "Which team should take this?",
    "company_pick": "Which company do you mean?",
    "member_offer": "Who should take this?",
    # The lane's own wording for the same question (contract 38): the customer read
    # "Outstanding for which document?" when it was asked, and a re-print that opened
    # with a different sentence reads as a second, different question.
    "outstanding_scope": "Outstanding for which document?",
    "outstanding_detail": "Which list would you like?",
    "kind_pick": "Which one do you mean?",
    "attachment_type_ask": "Which kind of file do you need?",
}


def _join_words(names: list[str]) -> str:
    """`a`, `a or b`, `a, b or c` - the list grammar the rung line reads with."""
    clean = [n for n in names if n]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    return ", ".join(clean[:-1]) + " or " + clean[-1]


def compose_question(pending: Any) -> Answer:
    """The ask, as an Answer: the header, the numbered roster, and the same pending back.

    A roster the customer can see is what a bare "1" answers next turn, so the options
    that are PRINTED here are exactly the options the tail stores - one list, never two.
    """
    # A did-you-mean is its own question (contract 26): the customer named something the
    # resolver could not place, so the ask offers what it DID find rather than asking them
    # to choose from a roster they did not ask for.
    did_you_mean = any((o.get("payload") or {}).get("did_you_mean") for o in pending.options)
    header = (
        "Did you mean:" if did_you_mean else _ASK_HEADERS.get(pending.kind, "Which one do you mean?")
    )
    lines = [header]
    labels: list[str] = []
    for option in pending.options:
        label = option.get("label")
        if label is None:
            continue
        stamp = option.get("stamp")
        printed = f"{label} - {stamp}" if stamp else str(label)
        labels.append(printed)
        lines.append(f"{option.get('position')}. {printed}")
    body = "\n".join(lines)

    # AC-1102: a question the LANE composed is re-printed in the lane's own bytes. The
    # outstanding report's detail offer is worded by the MCP presenter (R9's one
    # sentence for a single-scope report, the numbered list for two), and rebuilding it
    # from the roster produced two wordings for one offer, one after the other in the
    # same conversation. The offer's own text travels on the question's payload; every
    # other kind has no text of its own and reads the header table above.
    offered = (pending.payload or {}).get("filters") or {}
    verbatim = str(offered.get("offer_text") or "").strip() if isinstance(offered, dict) else ""
    if verbatim:
        body = verbatim
    action: dict[str, Any] = {
        "kind": "send_message",
        "text": body,
        "quick_replies": ", ".join(labels) if labels else None,
        "result_set": list(pending.options),
    }
    return Answer(sections=[], question=pending, offer=None, canned=[], files=[], actions=[action], text=body)

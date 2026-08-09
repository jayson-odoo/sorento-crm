"""Everything the warranty configuration screens are allowed to do (S7b).

ALL validation lives here; the routes are HTTP and Pydantic and nothing else. The
alternative - a guard in the route and another in the service - is how the POST
path and the PATCH path end up disagreeing about the same fact, which is precisely
the failure AC-P22 was written to catch.

Five rulings shape this module, and each one is a place the obvious version is
wrong.

**The overlap guard is the same arithmetic `policy_in_force` reads by** (AC-P2b):
both ends INCLUSIVE, a NULL `effective_to` meaning open-ended. It is applied on
PATCH as well as POST, because AC-P2 is phrased around "saving" and an edit is a
save - and it excludes the row being edited, because a policy does not overlap
itself and that false positive would refuse an edit that changed no date at all.

**The refusal names the other version AND its range.** "Overlaps an existing
policy" is not something an admin can act on: their next action is to pick a date,
and they cannot pick one they were not told. Where the conflicting policy is a
LATER one - the mis-dated-supersede case - the message also names the way out,
because AC-P26 deliberately has no undo endpoint and rests entirely on that
sentence existing.

**Supersede is one transaction, and every precondition is checked BEFORE anything
is mutated.** Half a supersede is the worst of the three states: the incumbent is
closed and no policy governs anything after that day, so every purchase from then
on answers `unknown`.

**A Kind delete is REFUSED while anything references it** (AC-P12), because
`warranty_terms.kind_id` and `warranty_kind_rules.kind_id` are both ON DELETE
CASCADE - the obvious hard delete silently removes warranty promises from every
policy at once, and the assessments that quoted them keep a snapshot pointing at a
term that no longer exists. A master-data delete must not be able to rewrite the
policy document. A POLICY delete does cascade its Terms, because a Term has no
life apart from the Policy that dates it, and the count travels on the row so the
confirmation can say so.

**Terms are loaded through their Policy, never by id alone** (AC-P9).
`WarrantyTerm` is deliberately not company-scoped - it is only ever reachable
through `policy_id` - which makes an unguarded nested route hand another company's
warranty terms to anyone who guesses an id. The Policy is loaded FIRST, under the
caller's scope, so one outside it 404s before a term is ever touched.

Nothing here recomputes a `warranty_assessment` (AC-P8). An assessment is what was
decided at the time, and silently rewriting it is how a verdict a consumer was told
stops matching the record.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from fastapi import status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.lookup import LookupOption, LookupSet
from app.models.resources import Attachment
from app.models.warranty import (
    WarrantyAssessment,
    WarrantyKindRule,
    WarrantyPolicy,
    WarrantyProductKind,
    WarrantyTerm,
)
from app.schemas.warranty_config import (
    KindCreate,
    KindRuleCreate,
    KindRuleTestRequest,
    KindRuleUpdate,
    KindUpdate,
    PolicyCreate,
    PolicyUpdate,
    TermCreate,
    TermUpdate,
)
from app.services.error_handler import AppException
from app.services.warranty_service import rank_kind_matches

# The lookup set `covered_defect_type_ids` points into. Named once: the Term editor
# and the label resolver must agree, or a picker offers options the labels cannot
# resolve.
DEFECT_TYPE_SET_KEY = "complaints_defect_type"

# Postgres has no `infinity` for the `date` type in a plain comparison here, and a
# NULL `effective_to` means open-ended. `date.max` is the comparison stand-in and
# never reaches a column.
_OPEN_ENDED = date.max


def _conflict(message: str) -> AppException:
    return AppException(status_code=status.HTTP_409_CONFLICT, message=message, code="CONFLICT")


def _unprocessable(message: str) -> AppException:
    return AppException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message=message,
        code="VALIDATION_ERROR",
    )


def _not_found(message: str) -> AppException:
    return AppException(
        status_code=status.HTTP_404_NOT_FOUND, message=message, code="NOT_FOUND"
    )


def _window(policy: WarrantyPolicy) -> str:
    """A policy's window in words an admin can act on."""
    start = policy.effective_from.isoformat() if policy.effective_from else "an unknown date"
    if policy.effective_to is None:
        return f"{start} onwards"
    return f"{start} to {policy.effective_to.isoformat()}"


class WarrantyConfigService:
    """The editor behind `/api/v1/warranty-management`."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ policies

    def _policy_or_404(self, policy_id: str) -> WarrantyPolicy:
        """The policy, under the caller's company scope.

        No manual company filter: `WarrantyPolicy` is a `CompanyScopedMixin`, so the
        session's scope is already injected into this SELECT by the global listener.
        Filtering again would be a second copy of the same rule that can disagree
        with the first - and one outside the scope is genuinely NOT FOUND for this
        caller, which is why it 404s rather than 403s.
        """
        row = self.db.query(WarrantyPolicy).filter(WarrantyPolicy.id == policy_id).first()
        if row is None:
            raise _not_found("Warranty policy not found. Someone might have deleted it already.")
        return row

    def _term_counts(self, policy_ids: Sequence[str]) -> Dict[str, int]:
        if not policy_ids:
            return {}
        rows = (
            self.db.query(WarrantyTerm.policy_id, func.count(WarrantyTerm.id))
            .filter(WarrantyTerm.policy_id.in_(list(policy_ids)))
            .group_by(WarrantyTerm.policy_id)
            .all()
        )
        return {str(pid): int(count) for pid, count in rows}

    def _attachment_names(self, attachment_ids: Iterable[Optional[str]]) -> Dict[str, str]:
        wanted = [a for a in set(attachment_ids) if a]
        if not wanted:
            return {}
        rows = (
            self.db.query(Attachment.id, Attachment.original_filename)
            .filter(Attachment.id.in_(wanted))
            .all()
        )
        return {str(aid): name for aid, name in rows}

    def _policy_dict(
        self,
        policy: WarrantyPolicy,
        *,
        term_counts: Optional[Dict[str, int]] = None,
        attachment_names: Optional[Dict[str, str]] = None,
    ) -> dict:
        counts = term_counts if term_counts is not None else self._term_counts([policy.id])
        names = (
            attachment_names
            if attachment_names is not None
            else self._attachment_names([policy.source_attachment_id])
        )
        return {
            "id": policy.id,
            "version": policy.version,
            "effective_from": policy.effective_from,
            "effective_to": policy.effective_to,
            "source_attachment_id": policy.source_attachment_id,
            "source_attachment_name": names.get(str(policy.source_attachment_id or "")),
            "policy_text": policy.policy_text,
            "term_count": counts.get(str(policy.id), 0),
            "created_at": policy.created_at,
            "updated_at": policy.updated_at,
        }

    def list_policies(
        self,
        *,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort: Optional[str] = None,
        dir: Optional[str] = None,
    ) -> dict:
        q = self.db.query(WarrantyPolicy)
        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.filter(
                or_(WarrantyPolicy.version.ilike(term), WarrantyPolicy.policy_text.ilike(term))
            )

        sortable = {
            "version": WarrantyPolicy.version,
            "effective_from": WarrantyPolicy.effective_from,
            "effective_to": WarrantyPolicy.effective_to,
            "created_at": WarrantyPolicy.created_at,
        }
        column = sortable.get((sort or "").strip(), WarrantyPolicy.effective_from)
        ordering = column.asc() if (dir or "").strip().lower() == "asc" else column.desc()

        total = q.count()
        rows = (
            q.order_by(ordering, WarrantyPolicy.id.asc())
            .offset(max(page - 1, 0) * limit)
            .limit(limit)
            .all()
        )
        term_counts = self._term_counts([r.id for r in rows])
        attachment_names = self._attachment_names([r.source_attachment_id for r in rows])
        return {
            "data": [
                self._policy_dict(r, term_counts=term_counts, attachment_names=attachment_names)
                for r in rows
            ],
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def get_policy(self, policy_id: str) -> dict:
        return self._policy_dict(self._policy_or_404(policy_id))

    def _assert_version_free(self, version: str, *, exclude_id: Optional[str] = None) -> None:
        """(company, version) is unique - Sorento's Version 15 and Mocha's Version 15
        are different documents that disagree on durations, so the uniqueness is
        per company and the scope listener supplies that half."""
        q = self.db.query(WarrantyPolicy).filter(WarrantyPolicy.version == version)
        if exclude_id:
            q = q.filter(WarrantyPolicy.id != exclude_id)
        if q.first() is not None:
            raise _conflict(
                f"Policy version {version} already exists for this company. "
                "Versions are unique per company."
            )

    def _overlapping_policy(
        self,
        *,
        effective_from: date,
        effective_to: Optional[date],
        exclude_id: Optional[str] = None,
    ) -> Optional[WarrantyPolicy]:
        """AC-P2b's arithmetic, once: two windows of the SAME company overlap when
        `a.from <= coalesce(b.to, infinity)` AND `b.from <= coalesce(a.to, infinity)`.

        Company scoping is the listener's job; policies of different companies are
        answers to different questions and never overlap each other.
        """
        q = self.db.query(WarrantyPolicy)
        if exclude_id:
            q = q.filter(WarrantyPolicy.id != exclude_id)
        q = q.filter(WarrantyPolicy.effective_from <= (effective_to or _OPEN_ENDED))
        q = q.filter(
            or_(
                WarrantyPolicy.effective_to.is_(None),
                WarrantyPolicy.effective_to >= effective_from,
            )
        )
        return q.order_by(WarrantyPolicy.effective_from.asc(), WarrantyPolicy.id.asc()).first()

    def _assert_no_overlap(
        self,
        *,
        effective_from: date,
        effective_to: Optional[date],
        exclude_id: Optional[str] = None,
    ) -> None:
        other = self._overlapping_policy(
            effective_from=effective_from, effective_to=effective_to, exclude_id=exclude_id
        )
        if other is None:
            return
        message = (
            f"Effective range overlaps policy {other.version} ({_window(other)}). "
            "A complaint is judged against the version in force on its purchase date, "
            "so two candidates make that answer arbitrary."
        )
        if other.effective_from and other.effective_from > effective_from:
            # The conflicting policy STARTS LATER, which is the mis-dated-supersede
            # shape (AC-P26). There is no undo endpoint precisely because this
            # sentence exists: delete the successor - a freshly superseded policy has
            # no Terms yet - and the reopen is then unrefused.
            message += (
                f" Delete policy {other.version} first, or change the dates."
            )
        raise _conflict(message)

    def create_policy(self, payload: PolicyCreate) -> dict:
        self._assert_version_free(payload.version)
        self._assert_no_overlap(
            effective_from=payload.effective_from, effective_to=payload.effective_to
        )
        row = WarrantyPolicy(
            version=payload.version,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            source_attachment_id=payload.source_attachment_id,
            policy_text=payload.policy_text,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._policy_dict(row)

    def update_policy(self, policy_id: str, payload: PolicyUpdate) -> dict:
        policy = self._policy_or_404(policy_id)
        # `exclude_unset` is what makes "set effective_to to null" distinguishable
        # from "did not mention effective_to". Without it AC-P26's recovery path -
        # reopening a mis-superseded policy - is not expressible at all, while every
        # other test still passes.
        changes = payload.model_dump(exclude_unset=True)

        version = changes.get("version", policy.version)
        effective_from = changes.get("effective_from", policy.effective_from)
        effective_to = (
            changes["effective_to"] if "effective_to" in changes else policy.effective_to
        )

        if effective_to is not None and effective_from is not None and effective_to < effective_from:
            raise _unprocessable(
                "The effective-to date cannot be before the effective-from date."
            )
        if version != policy.version:
            self._assert_version_free(version, exclude_id=policy.id)
        self._assert_no_overlap(
            effective_from=effective_from, effective_to=effective_to, exclude_id=policy.id
        )

        for field, value in changes.items():
            setattr(policy, field, value)
        self.db.commit()
        self.db.refresh(policy)
        return self._policy_dict(policy)

    def delete_policy(self, policy_id: str) -> dict:
        policy = self._policy_or_404(policy_id)
        # Hard delete. `warranty_terms.policy_id` is ON DELETE CASCADE, so the Terms
        # go with it - which is why the row carries `term_count` and the confirmation
        # names it (AC-P13).
        version = policy.version
        self.db.delete(policy)
        self.db.commit()
        return {"message": f"Warranty policy {version} deleted."}

    def _successor_of(self, policy: WarrantyPolicy) -> Optional[WarrantyPolicy]:
        """The policy that closed this one, derived rather than stored.

        It is the one whose window begins the day after this one ends - which is
        exactly why AC-P26 needs no predecessor column, and a stored "previous
        value" would be a second copy of a fact that drifts from the first.
        """
        if policy.effective_to is None:
            return None
        return (
            self.db.query(WarrantyPolicy)
            .filter(WarrantyPolicy.id != policy.id)
            .filter(WarrantyPolicy.effective_from == policy.effective_to + timedelta(days=1))
            .order_by(WarrantyPolicy.id.asc())
            .first()
        )

    def supersede_policy(self, policy_id: str, payload: PolicyCreate) -> dict:
        """AC-P2a. In ONE transaction: close the incumbent the day before the new
        version starts, and create the new version.

        Every precondition is checked before anything is mutated, so a refused
        supersede leaves the incumbent open. Closing it on the new start date would
        leave both in force for a day; closing it a day earlier would leave a hole,
        and a hole is an `unknown` verdict handed to a customer for no reason.
        """
        incumbent = self._policy_or_404(policy_id)

        if incumbent.effective_to is not None:
            # AC-P21. Superseding a CLOSED policy either rewrites a closed window or
            # opens a calendar gap. The refusal names the version that closed it,
            # because an admin told only "no" has nothing to do next.
            successor = self._successor_of(incumbent)
            closer = (
                f" It was closed by policy {successor.version}."
                if successor is not None
                else ""
            )
            raise _unprocessable(
                f"Policy {incumbent.version} already ends on "
                f"{incumbent.effective_to.isoformat()}, so it cannot be superseded."
                + closer
                + " Delete the later policy first if you need to republish it."
            )

        if payload.effective_from <= incumbent.effective_from:
            # AC-P21, the case the overlap check can never catch: the incumbent's new
            # `effective_to` would land BEFORE its own `effective_from`, and an
            # inverted range overlaps nothing, so the guard would report no conflict
            # while the policy silently governed no day at all.
            raise _unprocessable(
                f"The new version must start after policy {incumbent.version} starts "
                f"({incumbent.effective_from.isoformat()})."
            )

        self._assert_version_free(payload.version)
        # The incumbent is about to be closed the day before the new start, so by
        # construction it cannot overlap the new window - exclude it rather than
        # mutate first and check afterwards.
        self._assert_no_overlap(
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            exclude_id=incumbent.id,
        )

        try:
            incumbent.effective_to = payload.effective_from - timedelta(days=1)
            created = WarrantyPolicy(
                version=payload.version,
                effective_from=payload.effective_from,
                effective_to=payload.effective_to,
                source_attachment_id=payload.source_attachment_id,
                policy_text=payload.policy_text,
            )
            self.db.add(created)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(incumbent)
        self.db.refresh(created)
        return {"closed": self._policy_dict(incumbent), "created": self._policy_dict(created)}

    # --------------------------------------------------------------------- terms

    def _kind_or_404(self, kind_id: str) -> WarrantyProductKind:
        row = (
            self.db.query(WarrantyProductKind)
            .filter(WarrantyProductKind.id == kind_id)
            .first()
        )
        if row is None:
            raise _not_found("Warranty product kind not found.")
        return row

    def _assessment_counts(self, term_ids: Sequence[str]) -> Dict[str, int]:
        if not term_ids:
            return {}
        rows = (
            self.db.query(WarrantyAssessment.term_id, func.count(WarrantyAssessment.id))
            .filter(WarrantyAssessment.term_id.in_(list(term_ids)))
            .group_by(WarrantyAssessment.term_id)
            .all()
        )
        return {str(tid): int(count) for tid, count in rows}

    def _defect_labels(self, option_ids: Iterable[str]) -> Dict[str, str]:
        wanted = [o for o in set(option_ids) if o]
        if not wanted:
            return {}
        rows = (
            self.db.query(LookupOption.id, LookupOption.label)
            .filter(LookupOption.id.in_(wanted))
            .all()
        )
        return {str(oid): label for oid, label in rows}

    def _term_dict(
        self,
        term: WarrantyTerm,
        kind: WarrantyProductKind,
        *,
        assessment_counts: Dict[str, int],
        defect_labels: Dict[str, str],
    ) -> dict:
        ids = list(term.covered_defect_type_ids or [])
        return {
            "id": term.id,
            "policy_id": term.policy_id,
            "kind_id": term.kind_id,
            "kind_code": kind.code,
            "kind_name": kind.name,
            "part_name": term.part_name,
            "duration_months": term.duration_months,
            "is_lifetime": bool(term.is_lifetime),
            "covered_defect_type_ids": term.covered_defect_type_ids,
            "covered_defect_type_labels": (
                [defect_labels[str(i)] for i in ids if str(i) in defect_labels] if ids else None
            ),
            "installation_included": bool(term.installation_included),
            "registration_bonus_months": term.registration_bonus_months,
            "qualifications": term.qualifications,
            "exclusions": term.exclusions,
            "assessment_count": assessment_counts.get(str(term.id), 0),
            "created_at": term.created_at,
            "updated_at": term.updated_at,
        }

    def _terms_of(self, policy: WarrantyPolicy):
        return (
            self.db.query(WarrantyTerm, WarrantyProductKind)
            .join(WarrantyProductKind, WarrantyProductKind.id == WarrantyTerm.kind_id)
            .filter(WarrantyTerm.policy_id == policy.id)
            .order_by(WarrantyProductKind.sort_order.asc(), WarrantyProductKind.name.asc(),
                      WarrantyTerm.part_name.asc())
            .all()
        )

    def _rendered_terms(self, rows) -> List[dict]:
        assessment_counts = self._assessment_counts([t.id for t, _ in rows])
        defect_labels = self._defect_labels(
            [i for t, _ in rows for i in (t.covered_defect_type_ids or [])]
        )
        return [
            self._term_dict(
                term, kind, assessment_counts=assessment_counts, defect_labels=defect_labels
            )
            for term, kind in rows
        ]

    def list_terms(self, policy_id: str) -> List[dict]:
        policy = self._policy_or_404(policy_id)
        return self._rendered_terms(self._terms_of(policy))

    def list_terms_grouped_by_kind(self, policy_id: str) -> dict:
        """AC-P4: every Term of a Kind, together.

        A policy with no Terms answers an EMPTY group list, never a 404 - the CRUD
        standard renders every section, and a 404 makes a brand-new policy look
        broken.
        """
        policy = self._policy_or_404(policy_id)
        rows = self._terms_of(policy)
        rendered = self._rendered_terms(rows)
        by_term = {r["id"]: r for r in rendered}

        groups: List[dict] = []
        seen: Dict[str, dict] = {}
        for term, kind in rows:
            group = seen.get(kind.id)
            if group is None:
                group = {
                    "kind": {"id": kind.id, "code": kind.code, "name": kind.name},
                    "terms": [],
                }
                seen[kind.id] = group
                groups.append(group)
            group["terms"].append(by_term[term.id])
        return {"groups": groups, "total": len(rendered)}

    def _assert_term_shape(self, *, duration_months: Optional[int], is_lifetime: bool) -> None:
        """AC-P3 / AC-P3a / AC-P20: lifetime XOR a POSITIVE duration.

        The database enforces the same thing (`ck_warranty_terms_duration_xor_lifetime`)
        because the service is not the only writer - a seed script, a migration
        backfill and a psql session all bypass it. This half is the message.
        """
        if is_lifetime and duration_months is not None:
            raise _unprocessable(
                "A term is either lifetime or a number of months, never both."
            )
        if not is_lifetime:
            if duration_months is None:
                raise _unprocessable(
                    "A term needs either a duration in months or lifetime cover. "
                    "A term with neither answers 'unknown' on every complaint."
                )
            if duration_months <= 0:
                raise _unprocessable(
                    "A duration must be at least one month. A zero-month term tells a "
                    "customer their cover expired on the day they bought it."
                )

    def _assert_part_free(
        self,
        *,
        policy_id: str,
        kind_id: str,
        part_name: str,
        exclude_id: Optional[str] = None,
    ) -> None:
        q = (
            self.db.query(WarrantyTerm)
            .filter(WarrantyTerm.policy_id == policy_id)
            .filter(WarrantyTerm.kind_id == kind_id)
            .filter(WarrantyTerm.part_name == part_name)
        )
        if exclude_id:
            q = q.filter(WarrantyTerm.id != exclude_id)
        if q.first() is not None:
            raise _conflict(
                f"This policy already records a term for {part_name} on this product "
                "kind. Two rows for one part is two expiries for one promise."
            )

    def create_term(self, policy_id: str, payload: TermCreate) -> dict:
        policy = self._policy_or_404(policy_id)
        kind = self._kind_or_404(payload.kind_id)
        self._assert_term_shape(
            duration_months=payload.duration_months, is_lifetime=payload.is_lifetime
        )
        self._assert_part_free(
            policy_id=policy.id, kind_id=kind.id, part_name=payload.part_name
        )
        row = WarrantyTerm(
            policy_id=policy.id,
            kind_id=kind.id,
            part_name=payload.part_name,
            duration_months=payload.duration_months,
            is_lifetime=payload.is_lifetime,
            covered_defect_type_ids=payload.covered_defect_type_ids,
            installation_included=payload.installation_included,
            registration_bonus_months=payload.registration_bonus_months,
            qualifications=payload.qualifications,
            exclusions=payload.exclusions,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._rendered_terms([(row, kind)])[0]

    def _term_or_404(self, policy: WarrantyPolicy, term_id: str) -> WarrantyTerm:
        row = (
            self.db.query(WarrantyTerm)
            .filter(WarrantyTerm.id == term_id)
            .filter(WarrantyTerm.policy_id == policy.id)
            .first()
        )
        if row is None:
            # The right company but the wrong parent is the second half of AC-P9's
            # hazard: a route that loaded the term by id alone would edit a term
            # under a policy the URL never named.
            raise _not_found("Warranty term not found under this policy.")
        return row

    def update_term(self, policy_id: str, term_id: str, payload: TermUpdate) -> dict:
        policy = self._policy_or_404(policy_id)
        term = self._term_or_404(policy, term_id)
        changes = payload.model_dump(exclude_unset=True)

        kind_id = changes.get("kind_id", term.kind_id)
        kind = self._kind_or_404(kind_id)
        duration_months = (
            changes["duration_months"] if "duration_months" in changes else term.duration_months
        )
        is_lifetime = bool(
            changes["is_lifetime"] if "is_lifetime" in changes else term.is_lifetime
        )
        part_name = changes.get("part_name", term.part_name)

        self._assert_term_shape(duration_months=duration_months, is_lifetime=is_lifetime)
        if (kind_id, part_name) != (term.kind_id, term.part_name):
            self._assert_part_free(
                policy_id=policy.id,
                kind_id=kind_id,
                part_name=part_name,
                exclude_id=term.id,
            )

        for field, value in changes.items():
            setattr(term, field, value)
        self.db.commit()
        self.db.refresh(term)
        # Stored assessments are deliberately NOT recomputed (AC-P8): an assessment
        # is what was decided at the time.
        return self._rendered_terms([(term, kind)])[0]

    def delete_term(self, policy_id: str, term_id: str) -> dict:
        policy = self._policy_or_404(policy_id)
        term = self._term_or_404(policy, term_id)
        part_name = term.part_name
        # `warranty_assessments.term_id` is ON DELETE SET NULL and the snapshot
        # columns keep the verdict readable without it (AC-P8a). A cascade here would
        # delete the evidence behind an answer a human already acted on.
        self.db.delete(term)
        self.db.commit()
        return {"message": f"Warranty term {part_name} deleted."}

    # --------------------------------------------------------------------- kinds

    def _kind_rule_counts(self, kind_ids: Sequence[str]) -> Dict[str, int]:
        if not kind_ids:
            return {}
        rows = (
            self.db.query(WarrantyKindRule.kind_id, func.count(WarrantyKindRule.id))
            .filter(WarrantyKindRule.kind_id.in_(list(kind_ids)))
            .group_by(WarrantyKindRule.kind_id)
            .all()
        )
        return {str(kid): int(count) for kid, count in rows}

    def _kind_term_counts(self, kind_ids: Sequence[str]) -> Dict[str, int]:
        if not kind_ids:
            return {}
        rows = (
            self.db.query(WarrantyTerm.kind_id, func.count(WarrantyTerm.id))
            .filter(WarrantyTerm.kind_id.in_(list(kind_ids)))
            .group_by(WarrantyTerm.kind_id)
            .all()
        )
        return {str(kid): int(count) for kid, count in rows}

    def _kind_dict(
        self,
        kind: WarrantyProductKind,
        *,
        rule_counts: Dict[str, int],
        term_counts: Dict[str, int],
    ) -> dict:
        rule_count = rule_counts.get(str(kind.id), 0)
        term_count = term_counts.get(str(kind.id), 0)
        return {
            "id": kind.id,
            "code": kind.code,
            "name": kind.name,
            "consumer_label": kind.consumer_label,
            "consumer_icon": kind.consumer_icon,
            "sort_order": kind.sort_order or 0,
            "is_active": bool(kind.is_active),
            "rule_count": rule_count,
            "term_count": term_count,
            # AC-P17: the zero is a field, not a colour. Export, MCP and the AI
            # assistant all read this payload and none of them can see a CSS class.
            "has_no_rules": rule_count == 0,
            "has_no_terms": term_count == 0,
        }

    def list_kinds(
        self, *, query: Optional[str] = None, is_active: Optional[bool] = None, limit: int = 200
    ) -> List[dict]:
        q = self.db.query(WarrantyProductKind)
        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    WarrantyProductKind.code.ilike(term),
                    WarrantyProductKind.name.ilike(term),
                    WarrantyProductKind.consumer_label.ilike(term),
                )
            )
        if is_active is not None:
            q = q.filter(WarrantyProductKind.is_active.is_(is_active))
        rows = (
            q.order_by(WarrantyProductKind.sort_order.asc(), WarrantyProductKind.name.asc())
            .limit(limit)
            .all()
        )
        ids = [r.id for r in rows]
        rule_counts = self._kind_rule_counts(ids)
        term_counts = self._kind_term_counts(ids)
        return [
            self._kind_dict(r, rule_counts=rule_counts, term_counts=term_counts) for r in rows
        ]

    def list_kind_options(self, *, query: Optional[str] = None, limit: int = 200) -> List[dict]:
        q = self.db.query(WarrantyProductKind).filter(
            WarrantyProductKind.is_active.isnot(False)
        )
        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    WarrantyProductKind.code.ilike(term),
                    WarrantyProductKind.name.ilike(term),
                )
            )
        rows = (
            q.order_by(WarrantyProductKind.sort_order.asc(), WarrantyProductKind.name.asc())
            .limit(limit)
            .all()
        )
        return [{"id": r.id, "code": r.code, "name": r.name} for r in rows]

    def _assert_kind_code_free(self, code: str, *, exclude_id: Optional[str] = None) -> None:
        q = self.db.query(WarrantyProductKind).filter(WarrantyProductKind.code == code)
        if exclude_id:
            q = q.filter(WarrantyProductKind.id != exclude_id)
        if q.first() is not None:
            raise _conflict(
                f"A product kind with the code {code} already exists. The code is the "
                "seed's idempotence key, so it has to stay unique."
            )

    def _one_kind_dict(self, kind: WarrantyProductKind) -> dict:
        return self._kind_dict(
            kind,
            rule_counts=self._kind_rule_counts([kind.id]),
            term_counts=self._kind_term_counts([kind.id]),
        )

    def create_kind(self, payload: KindCreate) -> dict:
        self._assert_kind_code_free(payload.code)
        row = WarrantyProductKind(
            code=payload.code,
            name=payload.name,
            consumer_label=payload.consumer_label,
            consumer_icon=payload.consumer_icon,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._one_kind_dict(row)

    def update_kind(self, kind_id: str, payload: KindUpdate) -> dict:
        kind = self._kind_or_404(kind_id)
        changes = payload.model_dump(exclude_unset=True)
        code = changes.get("code", kind.code)
        if code != kind.code:
            self._assert_kind_code_free(code, exclude_id=kind.id)
        for field, value in changes.items():
            setattr(kind, field, value)
        self.db.commit()
        self.db.refresh(kind)
        return self._one_kind_dict(kind)

    def delete_kind(self, kind_id: str) -> dict:
        kind = self._kind_or_404(kind_id)
        term_count = self._kind_term_counts([kind.id]).get(str(kind.id), 0)
        rule_count = self._kind_rule_counts([kind.id]).get(str(kind.id), 0)
        if term_count or rule_count:
            # AC-P12. Both FKs are ON DELETE CASCADE, so the obvious hard delete
            # removes warranty promises from EVERY policy at once. The refusal names
            # both counts, because "1 term is using it" is a message an admin can act
            # on and "cannot delete" is one they escalate.
            raise _conflict(
                f"{kind.name} is still referenced by {term_count} term(s) and "
                f"{rule_count} rule(s). Remove those first - deleting this kind would "
                "take the terms with it."
            )
        name = kind.name
        self.db.delete(kind)
        self.db.commit()
        return {"message": f"Warranty product kind {name} deleted."}

    # ---------------------------------------------------------------- kind rules

    def _rule_dict(self, rule: WarrantyKindRule, kind: WarrantyProductKind) -> dict:
        return {
            "id": rule.id,
            "kind_id": rule.kind_id,
            "kind_code": kind.code,
            "kind_name": kind.name,
            "match_type": rule.match_type,
            "match_value": rule.match_value,
            "priority": rule.priority or 0,
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    def list_kind_rules(
        self, *, kind_id: Optional[str] = None, limit: int = 500
    ) -> List[dict]:
        q = (
            self.db.query(WarrantyKindRule, WarrantyProductKind)
            .join(WarrantyProductKind, WarrantyProductKind.id == WarrantyKindRule.kind_id)
        )
        if kind_id:
            q = q.filter(WarrantyKindRule.kind_id == kind_id)
        rows = (
            q.order_by(
                WarrantyProductKind.name.asc(),
                WarrantyKindRule.priority.desc(),
                WarrantyKindRule.match_value.asc(),
            )
            .limit(limit)
            .all()
        )
        return [self._rule_dict(rule, kind) for rule, kind in rows]

    def create_kind_rule(self, payload: KindRuleCreate) -> dict:
        kind = self._kind_or_404(payload.kind_id)
        row = WarrantyKindRule(
            kind_id=kind.id,
            match_type=payload.match_type,
            match_value=payload.match_value,
            priority=payload.priority,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._rule_dict(row, kind)

    def _rule_or_404(self, rule_id: str) -> WarrantyKindRule:
        row = self.db.query(WarrantyKindRule).filter(WarrantyKindRule.id == rule_id).first()
        if row is None:
            raise _not_found("Warranty kind rule not found.")
        return row

    def update_kind_rule(self, rule_id: str, payload: KindRuleUpdate) -> dict:
        rule = self._rule_or_404(rule_id)
        changes = payload.model_dump(exclude_unset=True)
        kind = self._kind_or_404(changes.get("kind_id", rule.kind_id))
        for field, value in changes.items():
            setattr(rule, field, value)
        self.db.commit()
        self.db.refresh(rule)
        return self._rule_dict(rule, kind)

    def delete_kind_rule(self, rule_id: str) -> dict:
        rule = self._rule_or_404(rule_id)
        value = rule.match_value
        self.db.delete(rule)
        self.db.commit()
        return {"message": f"Warranty kind rule {value} deleted."}

    def test_kind_rules(self, payload: KindRuleTestRequest) -> dict:
        """AC-P6 / AC-P6b / AC-P6c: the tester, answering from the PRODUCTION ranking.

        `rank_kind_matches` is the engine's own order - a tester that ranked for
        itself would agree with production right up to the day it matters, and the
        day it matters is the day an admin uses it to decide a mapping is safe.

        The candidate rule is a TRANSIENT model instance that is never added to the
        session, and it is recognised in the result BY IDENTITY, so no marker column
        and no extra field on `_RuleMatch` is needed.
        """
        candidate = None
        if payload.candidate_rule is not None:
            candidate = WarrantyKindRule(
                kind_id=payload.candidate_rule.kind_id,
                match_type=payload.candidate_rule.match_type,
                match_value=payload.candidate_rule.match_value,
                priority=payload.candidate_rule.priority,
            )

        matches = rank_kind_matches(
            self.db,
            product_code=payload.product_code,
            category_code=payload.category_code,
            product_name=payload.product_name,
            extra_rules=(candidate,) if candidate is not None else (),
        )

        rendered: List[dict] = []
        for rank, match in enumerate(matches, start=1):
            is_candidate = candidate is not None and match.rule is candidate
            rendered.append(
                {
                    "rank": rank,
                    "rule": {
                        # An unsaved rule has no id. Inventing one lets the frontend
                        # link to a row that does not exist.
                        "id": match.rule.id,
                        "kind_id": match.rule.kind_id,
                        "match_type": match.rule.match_type,
                        "match_value": match.rule.match_value,
                        "priority": match.rule.priority or 0,
                        "is_candidate": is_candidate,
                    },
                    "kind": {
                        "id": match.kind.id,
                        "code": match.kind.code,
                        "name": match.kind.name,
                    },
                    "matched_length": match.matched_length,
                    "is_candidate": is_candidate,
                }
            )

        head = rendered[0] if rendered else None
        return {
            "resolved_kind": head["kind"] if head else None,
            "deciding_rule": head["rule"] if head else None,
            "matches": rendered,
        }

    # -------------------------------------------------------------- defect types

    def list_defect_types(self, *, limit: int = 500) -> List[dict]:
        """AC-P18. Returns `lookup_options.id`, NOT its `value`: the `uuid[]` column
        stores ids, and a varchar compared to a uuid column matches nothing."""
        rows = (
            self.db.query(LookupOption)
            .join(LookupSet, LookupSet.id == LookupOption.set_id)
            .filter(LookupSet.set_key == DEFECT_TYPE_SET_KEY)
            .filter(LookupOption.is_active.isnot(False))
            .order_by(LookupOption.sort_order.asc(), LookupOption.label.asc())
            .limit(limit)
            .all()
        )
        return [{"id": r.id, "label": r.label} for r in rows]

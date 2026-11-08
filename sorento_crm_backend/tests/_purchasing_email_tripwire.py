"""FP-EMAIL-ONE-TRIGGER regression guard: the shared harness of the purchasing-email tripwire.

Owner rule (6 Nov 2026): "I only want the email to purchasing to have 1 trigger, which is this
button" (the Fulfilment Planning board's Confirm; Publish amendment is his named exception).
Owner, 18:10: if any integration / sync path ever emails purchasing again, a test must fail.

`Tripwire.arm` switches ON a purchasing handover automation and a changed-with-links
automation whose conditions pass for every order, mailing a `.invalid` address only, and
watches three things a regression would leave:
- `AutomationService.dispatch_event` calls for those two triggers (recorded by a spy, then
  replayed through the real `dispatch_event` on the test's own session by `snapshot`);
- automation email Notifications to the tripwire address (what Outgoing Mails lists);
- `email_outbox` rows to the tripwire address (what the drainer sends).

`positive_control` proves the watch can see an email at all, in the same harness: a write
marked by `mark_purchasing_email_trigger` (what the board Confirm does) must trip it. Without
that, a "zero emails" assertion could pass because the harness was blind.

Used by `tests/test_purchasing_email_tripwire_so_po.py` and
`tests/test_purchasing_email_tripwire_docs.py`; listed in
`tests/test_lessons_learnt_regressions.py`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text

from app.models.automation import Automation
from app.models.email_template import EmailTemplate

TRIPWIRE_ADDRESS = "purchasing-tripwire@example.invalid"
PURCHASING_TRIGGERS = ("order_inquiry_handover", "order_inquiry_changed_with_links")


@dataclass
class Tripwire:
    db: object
    dispatches: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    real_dispatch: object = None

    @classmethod
    def arm(cls, db, monkeypatch) -> "Tripwire":
        from app.services.automation_service import AutomationService
        from app.services.project_order_inquiry_service import (
            register_order_inquiry_post_commit_dispatch,
        )

        register_order_inquiry_post_commit_dispatch()
        real_dispatch = AutomationService.dispatch_event
        template = EmailTemplate(
            code=f"zzt-tripwire-{uuid.uuid4().hex[:12]}", name="ZZT tripwire",
            subject="OI: {{ handover.subject_scope if handover else 'changed' }}",
            body_html="<p>tripwire</p>", body_text="tripwire",
        )
        db.add(template)
        db.flush()
        for trigger in PURCHASING_TRIGGERS:
            db.add(Automation(
                name=f"ZZT tripwire {trigger}", trigger_type=trigger, enabled=True,
                email_template_id=template.id, conditions_json=None,
                recipient_config={
                    "user_ids": [], "role_ids": [], "extra_emails": [TRIPWIRE_ADDRESS],
                    "include_actor": False, "one_email": True,
                },
            ))
        db.commit()
        wire = cls(db)

        def spy(self, trigger_type, *, context, source_kind, source_id):
            # Recorded, not run here: the drain calls this on a fresh SessionLocal, which in
            # tests is not this test's scratch schema, and running it on the test's own
            # connection mid-commit breaks its savepoints. `snapshot` replays it for real.
            if trigger_type in PURCHASING_TRIGGERS:
                wire.dispatches.append(trigger_type)
                wire.pending.append((trigger_type, context, source_kind, source_id))
            return {"trigger_type": trigger_type, "fired": 0, "results": []}

        monkeypatch.setattr(AutomationService, "dispatch_event", spy)
        wire.real_dispatch = real_dispatch
        return wire

    def _replay(self) -> None:
        """Run every recorded purchasing dispatch through the REAL `dispatch_event` on the
        test's own session: the automation run, the Notification Outgoing Mails lists and the
        send queue's rows land where this test can read them."""
        from app.services.automation_service import AutomationService

        pending, self.pending = self.pending, []
        for trigger_type, context, source_kind, source_id in pending:
            self.real_dispatch(
                AutomationService(self.db), trigger_type, context=context,
                source_kind=source_kind, source_id=source_id,
            )

    # ------------------------------------------------------------------ the watch
    def mails(self) -> int:
        return self.db.execute(text(
            "SELECT count(*) FROM notifications n "
            "WHERE n.type = 'automation_email' "
            "AND CAST(n.data ->> 'recipient_emails' AS text) LIKE :addr"
        ), {"addr": f"%{TRIPWIRE_ADDRESS}%"}).scalar()

    def outbox(self) -> int:
        return self.db.execute(text(
            "SELECT count(*) FROM email_outbox WHERE recipient_email = :addr"
        ), {"addr": TRIPWIRE_ADDRESS}).scalar()

    def snapshot(self) -> tuple:
        self._replay()
        self.db.expire_all()
        return (len(self.dispatches), self.mails(), self.outbox())

    def assert_silent_since(self, before: tuple, scenario: str) -> None:
        after = self.snapshot()
        assert after == before, (
            f"{scenario}: an integration path emailed purchasing "
            f"(dispatches, Outgoing Mails, email_outbox) went {before} -> {after}; "
            f"triggers {self.dispatches}. Owner rule 6 Nov 2026: only the board Confirm "
            "(and Publish amendment) may email purchasing."
        )

    def assert_tripped_since(self, before: tuple) -> None:
        after = self.snapshot()
        # The `email_outbox` row is written later by the send job (`notification_tasks`, on the
        # worker's own session), which this harness does not run, so the control asks for the
        # dispatch and the Outgoing Mails row; scenarios still assert zero outbox rows, which
        # catches any path that writes one directly.
        assert after[0] > before[0] and after[1] > before[1], (
            f"positive control: the harness saw no email ({before} -> {after}); the tripwire "
            "is blind and its zero assertions prove nothing"
        )

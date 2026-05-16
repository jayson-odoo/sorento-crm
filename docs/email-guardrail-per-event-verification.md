# Per-Event Email Outbox Verification

Run timestamp: 2026-05-16T14:48:16.585193Z

Each row triggers the actual producer path that fires when n8n / a user / a scheduled task creates the event, then asserts a row in `email_outbox` with the right `event_key` reaches `status=sent` after the drainer runs. SMTP send is mocked so this script does not depend on a mail server.

**23 / 23 events PASS**

| Event | Result | Description | Detail | Outbox row |
|---|---|---|---|---|
| `password_reset` | **PASS** | Reset password chokepoint (enqueue path) | sent=1 rows=1 | ac267671-8e17-4714-be10-6735f162fe85 |
| `user_invitation` | **PASS** | User invitation via NotificationService.create | sent=1 rows=1 | 43a6a90b-c823-4c4b-8b91-e368e728263c |
| `purchase_request_approval_link` | **PASS** | PR approval link (enqueue path) | sent=1 rows=1 | d8438bd7-ecdb-44de-b819-863de4497a66 |
| `purchase_request_approved` | **PASS** | PR approved (NotificationService.create) | sent=1 rows=1 | 86c93254-b36a-4dd8-88ff-a1e504a693a8 |
| `purchase_request_rejected` | **PASS** | PR rejected (NotificationService.create) | sent=1 rows=1 | 58d7411e-32eb-46c1-96ad-fd230b6bd57a |
| `stock_inquiry_created` | **PASS** | Stock inquiry internal (notification type stock_inquiry_notification) | sent=1 rows=1 | fb56386f-8de5-403b-8a32-b11869496332 |
| `stock_inquiry_created_external` | **PASS** | Stock inquiry external (same producer, async path) | sent=1 rows=1 | f24f6f58-c36f-4fcb-b414-8a2b87a81558 |
| `complaint_created_external` | **PASS** | Complaint portal (notification type complaint_notification) | sent=1 rows=1 | d07db7cf-b590-4d5d-a2f9-a7e879993ba3 |
| `ticket_assigned` | **PASS** | Ticket assigned (notification type ticket_assigned) | sent=1 rows=1 | 13377f41-0957-42b1-8d69-93f0055135fe |
| `ticket_team_new` | **PASS** | Ticket new in team queue | sent=1 rows=1 | f317d0e0-95dd-4c49-9301-34d08bfc58a5 |
| `ticket_responded` | **PASS** | Ticket responded | sent=1 rows=1 | ca7559f4-0df3-45a4-933c-491c9a6acf44 |
| `ticket_resolved` | **PASS** | Ticket resolved | sent=1 rows=1 | 759deca2-f693-438f-9466-96f18fbec2f8 |
| `external_product_attachment` | **PASS** | Product attachment linkage via external endpoint helper | sent=1 rows=1 | 723a628e-c5e4-4873-9955-117788c4db97 |
| `external_promotion_uploader_notice` | **PASS** | Promotion-created uploader notice | sent=2 rows=2 | c7177022-f9e9-4f9b-a784-ae444690ac94 |
| `external_form_created` | **PASS** | Form created via external endpoint | sent=2 rows=2 | 47a7d621-f28a-482e-a875-c6437245ea67 |
| `external_packing_list_created` | **PASS** | Packing list created via external endpoint | sent=2 rows=2 | b8547bff-8920-4c19-9610-e8ea0eba73b1 |
| `form_sla_assigned` | **PASS** | Form SLA assigned (notif type form_sla event_type assigned) | sent=1 rows=1 | 2a7411e1-5ade-41df-a3ef-0ee3123073f0 |
| `form_sla_escalated` | **PASS** | Form SLA escalated (notif type form_sla event_type escalated) | sent=1 rows=1 | d806fe14-0c93-4caf-80d5-a2f97e63747a |
| `form_sla_updated` | **PASS** | Form SLA updated (notif type form_sla event_type other) | sent=1 rows=1 | 868a4066-fbef-4132-98f4-322c2d280386 |
| `import_job_completed` | **PASS** | Import job finished/failed notification | sent=1 rows=1 | f0bd62f5-9ad0-4a39-947a-5f1ffe4aa880 |
| `workflow_form_state_transition` | **PASS** | Workflow form state transition | sent=1 rows=1 | 574e3417-b577-41b4-b10c-361daa2fcdf7 |
| `daily_sla_summary` | **PASS** | Daily SLA summary (enqueue path) | sent=1 rows=1 | 9be95309-133a-4458-9823-39e66ee7f0f6 |
| `notification_delivery` | **PASS** | Generic fallback for unmapped notification types | sent=1 rows=1 | 962fec14-224f-481d-8b7e-11eb4bff959f |

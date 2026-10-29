# Context assembly for agentic CRM

Proposed design, reflecting owner discussion on 29 October. The agent receives conversation plus task state plus tools and fresh evidence. Neither a slot-state-only prompt nor an ever-growing full transcript is sufficient.

Store the conversation under existing access/retention rules. For short sessions include all relevant turns; once large, preserve recent exact turns and an incremental summary of the older task context. The runner can retrieve original excerpts by task/message reference. User corrections supersede earlier assumptions without erasing action receipts.

Each call includes: trusted behavior and capability policy; current objective/constraints; latest user input; recent exact dialogue; older task summary; resolved entities with source/confidence; fresh relevant CRM facts; task status/completed actions/pending choices; current permitted capabilities; active assistant tool calls and tool results in provider-native-compatible sequence. Token budget prioritizes current instruction, unresolved decisions and active tool protocol. Large tool outputs are paginated, not silently cut. Retrieval uses task relevance and access scope, not just semantic similarity.

Server-only state includes authentication credentials, authorization decisions, operation idempotency, leases and complete audit receipts. Models may see useful actor labels and permitted choices but do not supply authority. Store opaque provider continuation only as needed with appropriate access/retention; do not expose private reasoning or use it as the business audit trail.

Example: user requests a real form submission, later changes quantity, then supplies a missing required field. Keep those exact recent messages, updated proposed field values and provenance, unresolved required fields and current form schema. On resume fetch current business state and permissions. After submission preserve the saved record/operation receipt, so a subsequent question does not cause a second submission.

Evaluation: corrections across compaction, reference to an older attachment, side question then resume, stale amounts, conflicting entity matches, long tool output, provider continuation, unauthorized historical retrieval, prompt injection in quoted records, and crash after a successful mutation. Verify both correct task outcome and absence of duplicated writes.

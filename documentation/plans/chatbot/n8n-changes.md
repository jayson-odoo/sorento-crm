# n8n changes, per slice (chatbot turn engine)

The CRM side of this program is tracked in `PLAN-chatbot-turn-engine.md`; this file is the
n8n side, written by the n8n owner session as each slice is designed and pasted here
verbatim so the two halves of a promote are readable in one place.

One section per slice, appended on that slice's own branch. A slice that has not been
designed yet has no section - absence means "not decided", never "no change needed".

## S1 (from help-crm, the n8n owner session, 5 Sep; paste verbatim into documentation/plans/chatbot/n8n-changes.md)

Spine head `get-session-vars -> Call 'sub-query-reformulator' -> check-access -> build-ctx -> route-turn` is replaced by `chat-turn` (httpRequest v4.3, POST https://fe-sorento.foundryx.my/api/v1/external/chat/turn, cred crm-n8n-auth, body `{envelope: {...<queue item>, media}}`, timeout 60 s, continueErrorOutput -> sub-error-logger) -> `head-arm` (Switch v3.4: `duplicate` [$json.duplicate true -> no successor], `finished` [$json.delegate ?? 'NONE' == 'NONE' -> send-crm-reply = sendmsg with reply.text], fallback `delegate` -> build-ctx) -> `build-ctx` (one line: re-emits {ctx: response.ctx}) -> `route-turn` (one line: re-emits response.item) -> existing `route` Switch. Old five nodes renamed `(pre-S1)`, disabled, edge-less, deleted at S8 (AC-802). Clone adds `is_test: true` inside envelope (G11) and retires the session-injection / mock-parser / chat-stateful session guards (G6/G8/G9) because those inputs now ride inside the envelope. Built as stage `s1` in the n8n repo's spine-next pipeline (branch feat/s1-chat-turn-head); active node count unchanged, +12 total until S8.

Precondition: the endpoint answers on fe-sorento (401/422 on an empty POST). Dry run writes exactly one `chatbot.turns` row (is_test true) and nothing else (D14); proof tests listed in the plan.


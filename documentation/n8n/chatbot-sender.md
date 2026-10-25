# n8n: `sorento-chatbot-sender` (CHAT-SPEED direct ingress)

For the owner to import. Crew makes no prod change. Plan:
`documentation/plans/chatbot/PLAN-chat-speed-ingress.md`.

## What it does

When `system_settings.chatbot_direct_ingress_mode` is on, the CRM's own respond.io webhook
starts a turn for a fresh incoming text, without waiting for `sorento-main` and
`sorento-dispatcher`. When the turn finishes, the CRM POSTs its actions here. This workflow
executes them in order, exactly as the spine does after `/chat/turn`. The CRM still never
sends (D9).

`sorento-main` and `sorento-dispatcher` stay exactly as they are. Their copy of the same
message reaches `/chat/turn` a few seconds later and comes back `duplicate: true`, and the
spine's `duplicate` arm sends nothing.

## Import

1. Import `chatbot-sender.workflow.json`. It imports inactive.
2. **Credentials:**
   - On the `chatbot-sender` webhook node: a new Header Auth credential, header name
     `X-Chatbot-Sender-Key`, value a long random string.
   - On `assign_conversation` and `add_comment`: the existing respond.io credential (the
     one named `sorento-api` in the SLA escalation workflow).
3. **The three Execute Workflow nodes** carry placeholder ids. Point each one at the sub the
   spine's action Switch already calls for that kind, with the same inputs the spine maps:

   | node | spine node to copy | inputs (from the item: `action.*`, `contact_id`, `turn_id`, `ctx`) |
   |---|---|---|
   | `send_message` | the sendmsg sub (`sorento-sub-respond-sendmsg-respond...`, as the spine's `sendmsg-action`) | the sub's own input names: `contact_identifer` = `contact_id`, `message` = `action.text`, `quick_reply` = `action.quick_replies` joined as the spine joins them, `result_set` = `action.result_set` (numbered follow-ups resolve against it), `turn_id`, and `contact` = `ctx.contact` (else `{id: contact_id}`): the sub saves the contact's phone and name with the message record |
   | `send_attachments` | `sub-send-attachments` (as `send-attachments`) | `attachments_src`, `reply`; plus the body's `ctx` (the sub addresses the customer by `ctx.contact.id`), with `ctx.text.message.message.attachment` deep-defaulted to `{}` so the link fallback does not throw on a turn with no text or attachment |
   | `update_contact_fields` | the spine's contact-field write (clears `is_human_intervened`) | `fields` (`{name: value}`) |

   If the spine's executor is easier to copy as a block, paste it after `action-kind`
   instead. The body the CRM sends has `/chat/turn`'s own response keys (`turn_id`,
   `is_test`, `duplicate`, `delegate`, `branch_kind`, `actions`, `reply`, `ctx`) plus
   `contact_id`, so only the source of the expressions changes, from the `chat-turn` node to
   `$('explode-actions').item.json` (`explode-actions` puts `ctx` on every item). The actions
   arrive split as `/chat/turn` sends them: a long reply is several `send_message` actions.
4. Activate it, and copy its production webhook URL.

## CRM side (owner, on the CRM screens)

1. **System > Respond Workspaces**, edit the default workspace, then **Chatbot sender**: paste
   the webhook URL and the Header Auth value as the sender key. The URL must be https and must
   not resolve to a private address.
2. **Settings > Chatbot**, **Direct ingress**: choose `Listed contacts` and list your own
   respond.io contact id first, then `All contacts` once it behaves.
3. **Rollback** is `Off`, effective on the next message with no deploy.

## Precondition (owner read at rollout)

The CRM's respond.io webhook must be live, with the signing keys saved under Settings >
Integrations. Crew saw signed deliveries succeed on 10-15 Oct, but reading the prod keys is
the owner's step.

## What it costs and what it does not touch

- One respond.io contact GET per direct text (the takeover flag is not in the webhook
  body), about what `findcontact` already costs inside the producer.
- Media, human-held contacts, stale or duplicate messages, bursts over 30 per second, and
  anything past the API's 8 direct turns in flight per process stay on the n8n path.
  Nothing in `sorento-main` changes.

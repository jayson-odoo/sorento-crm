'use client';

import { useState } from 'react';
import { Loader2, Plus, SendHorizonal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { WhatsAppText } from '@/components/chatbot/WhatsAppText';
import { useAgentConsole } from '../hooks/useAgentConsole';
import {
  ActionOutcome,
  ActionsBlock,
  Bubble,
  ProposalActions,
  ReplyMeta,
  StepsDisclosure,
  fetchContactOptions,
} from './AgentReplyParts';
import {
  type AgentConversationTurn,
  type AgentPendingAction,
  type AgentReplyMeta,
} from '../types/agentConsole.types';

/** Reloaded history carries the same chips as a fresh reply, when the turn stored them. */
function metaFromTurn(turn: AgentConversationTurn): AgentReplyMeta | null {
  const tools = turn.tool_calls ?? [];
  if (turn.rounds == null && tools.length === 0 && !turn.limit_hit) return null;
  return {
    rounds: turn.rounds ?? null,
    tool_calls: tools,
    limit_hit: turn.limit_hit ?? null,
  };
}

export default function AgentConsole() {
  const agent = useAgentConsole();
  const [draft, setDraft] = useState('');

  const submit = () => {
    const text = draft.trim();
    if (!text || agent.sending || !agent.contactId) return;
    setDraft('');
    agent.send(text);
  };

  return (
    <div
      className="flex min-h-[70dvh] flex-col gap-3 lg:h-[calc(100dvh-16rem)]"
      data-testid="agent-console"
    >
      <div className="flex flex-wrap items-end gap-3 border-b pb-3">
        <div className="min-w-[220px] flex-1 sm:flex-none">
          <Label className="mb-1 block text-xs text-muted-foreground">
            Contact
          </Label>
          <SearchableSelect
            value={agent.contactId ?? ''}
            onChange={() => {
              /* handled via onOptionChange, which also carries the label */
            }}
            onOptionChange={(option) => {
              if (option) agent.setContact(option.value, option.label);
            }}
            fetchOptions={fetchContactOptions}
            selectedOption={
              agent.contactId
                ? { value: agent.contactId, label: agent.contactLabel }
                : undefined
            }
            placeholder="Pick a contact..."
            size="sm"
          />
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={!agent.contactId || agent.startingNew || agent.sending}
          onClick={agent.startNew}
        >
          <Plus className="size-3.5" />
          New conversation
        </Button>
      </div>

      <div
        className="min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden pr-1"
        data-testid="agent-console-thread"
      >
        {agent.contactId && agent.loading ? (
          <div
            role="status"
            className="space-y-3"
            aria-label="Loading the conversation"
          >
            <div className="h-9 w-2/3 animate-pulse rounded-2xl bg-muted" />
            <div className="ms-auto h-9 w-1/2 animate-pulse rounded-2xl bg-muted" />
          </div>
        ) : null}
        {agent.contactId &&
        !agent.loading &&
        !agent.notice &&
        agent.turns.length === 0 &&
        !agent.pendingText ? (
          <div className="py-10 text-center" data-testid="agent-console-empty">
            <p className="text-sm font-medium">No messages yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Ask about stock, incoming shipments, orders or sales for this
              contact.
            </p>
          </div>
        ) : null}
        {agent.turns.map((turn) => (
          <div key={turn.turn_id} className="space-y-3">
            <Bubble role="user">
              <p className="whitespace-pre-wrap break-words">{turn.text}</p>
            </Bubble>
            {turn.reply_text ? (
              <Bubble role="agent">
                <p className="whitespace-pre-wrap break-words">
                  <WhatsAppText text={turn.reply_text} />
                </p>
                {turn.actions && turn.actions.length > 0 ? (
                  <ActionsBlock actions={turn.actions} />
                ) : null}
                {(() => {
                  const meta =
                    agent.metaByTurn[turn.turn_id] ?? metaFromTurn(turn);
                  return meta ? <ReplyMeta meta={meta} /> : null;
                })()}
                {turn.steps && turn.steps.rounds > 0 ? (
                  <StepsDisclosure steps={turn.steps} />
                ) : null}
                {agent.pendingAction &&
                agent.pendingAction.turn_id === turn.turn_id &&
                !agent.outcomeByTurn[turn.turn_id] ? (
                  <ProposalActions
                    action={agent.pendingAction}
                    busy={agent.deciding}
                    onConfirm={() =>
                      agent.confirmAction(
                        (agent.pendingAction as AgentPendingAction).id,
                        turn.turn_id,
                      )
                    }
                    onCancel={() =>
                      agent.cancelAction(
                        (agent.pendingAction as AgentPendingAction).id,
                        turn.turn_id,
                      )
                    }
                  />
                ) : null}
              </Bubble>
            ) : null}
            {agent.outcomeByTurn[turn.turn_id] &&
            !(turn.actions && turn.actions.some((a) => a.status !== 'proposed')) ? (
              <ActionOutcome outcome={agent.outcomeByTurn[turn.turn_id]} />
            ) : null}
          </div>
        ))}
        {agent.pendingText ? (
          <>
            <Bubble role="user">
              <p className="whitespace-pre-wrap break-words">
                {agent.pendingText}
              </p>
            </Bubble>
            <Bubble role="agent">
              <p className="flex items-center gap-1.5 italic text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                Working...
              </p>
            </Bubble>
          </>
        ) : null}
        {agent.notice ? (
          <p role="alert" className="text-sm text-destructive">
            {agent.notice}
          </p>
        ) : null}
      </div>

      <div className="flex items-end gap-2 border-t pt-3">
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Ask about stock, orders or sales"
          rows={2}
          disabled={agent.sending || !agent.contactId}
          className="min-w-0 flex-1 resize-none"
          aria-label="Message"
        />
        <Button
          type="button"
          size="icon"
          aria-label="Send"
          disabled={agent.sending || !agent.contactId || !draft.trim()}
          onClick={submit}
        >
          <SendHorizonal className="size-4" />
        </Button>
      </div>
    </div>
  );
}

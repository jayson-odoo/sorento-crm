'use client';

import { useState } from 'react';
import { Check, Loader2, Plus, SendHorizonal, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { WhatsAppText } from '@/components/chatbot/WhatsAppText';
import { getRespondContactsOutbound } from '../../respond-contacts/services/respondContactOutboundService';
import { useAgentConsole } from '../hooks/useAgentConsole';
import {
  AGENT_HIDDEN_TOOLS,
  AGENT_LIMIT_LABELS,
  agentToolLabel,
  type AgentActionResponse,
  type AgentConversationAction,
  type AgentConversationTurn,
  type AgentPendingAction,
  type AgentReplyMeta,
  type AgentSteps,
} from '../types/agentConsole.types';

async function fetchContactOptions(
  query: string,
): Promise<SearchableSelectOption[]> {
  const result = await getRespondContactsOutbound({
    pageIndex: 0,
    pageSize: 20,
    searchQuery: query,
  });
  return result.data
    .filter((row) => Boolean(row.respond_io_id))
    .map((row) => ({
      value: row.respond_io_id as string,
      label: row.name || row.phone_number || (row.respond_io_id as string),
      description: row.name && row.phone_number ? row.phone_number : undefined,
    }));
}

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

function Bubble({
  role,
  children,
}: {
  role: 'user' | 'agent';
  children: React.ReactNode;
}) {
  const isUser = role === 'user';
  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-2xl px-3 py-2.5 text-sm leading-relaxed shadow-sm',
          isUser ? 'bg-primary/15 text-foreground' : 'bg-muted text-foreground',
        )}
      >
        {children}
      </div>
    </div>
  );
}

/** The turn's steps, collapsed until asked for: rounds, tokens and each tool call with its time. */
function StepsDisclosure({ steps }: { steps: AgentSteps }) {
  const [open, setOpen] = useState(false);
  const calls = steps.tool_calls.filter((c) => !AGENT_HIDDEN_TOOLS.has(c.name));
  return (
    <div
      className="mt-1 text-xs text-muted-foreground"
      data-testid="agent-steps"
    >
      <button
        type="button"
        className="underline-offset-2 hover:underline"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        Steps
      </button>
      {open ? (
        <ul className="mt-1 space-y-0.5">
          <li>{steps.rounds === 1 ? '1 round' : `${steps.rounds} rounds`}</li>
          <li>
            Tokens: {steps.prompt_tokens.toLocaleString('en-US')} in,{' '}
            {steps.completion_tokens.toLocaleString('en-US')} out
          </li>
          {calls.map((call, index) => (
            <li key={`${call.name}-${index}`}>
              {call.detail
                ? call.detail
                : `${agentToolLabel(call.name)}: ${call.status} (${call.ms} ms)`}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ReplyMeta({ meta }: { meta: AgentReplyMeta }) {
  const rounds = meta.rounds;
  return (
    <div
      className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground"
      data-testid="agent-reply-meta"
    >
      {rounds == null ? null : (
        <span>{rounds === 1 ? '1 round' : `${rounds} rounds`}</span>
      )}
      {meta.tool_calls
        .filter((call) => !AGENT_HIDDEN_TOOLS.has(call.name))
        .map((call, index) => (
          <Badge key={`${call.name}-${index}`} variant="secondary" size="sm">
            {agentToolLabel(call.name)}: {call.status}
          </Badge>
        ))}
      {meta.limit_hit ? (
        <span>
          Stopped: {AGENT_LIMIT_LABELS[meta.limit_hit] ?? meta.limit_hit}
        </span>
      ) : null}
    </div>
  );
}

/** Confirm / Cancel under the reply that proposed the changes. The lines are in the reply itself. */
function ProposalActions({
  action,
  busy,
  onConfirm,
  onCancel,
}: {
  action: AgentPendingAction;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const count = action.lines.length;
  return (
    <div
      className="mt-2 flex flex-wrap items-center gap-2 border-t pt-2"
      data-testid="agent-proposal"
    >
      <Button
        type="button"
        size="sm"
        className="gap-1.5"
        disabled={busy}
        onClick={onConfirm}
      >
        {busy ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <Check className="size-3.5" />
        )}
        {count === 1 ? 'Confirm change' : `Confirm ${count} changes`}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="gap-1.5"
        disabled={busy}
        onClick={onCancel}
      >
        <X className="size-3.5" />
        Cancel
      </Button>
    </div>
  );
}

const OUTCOME_TONE: Record<string, 'success' | 'warning' | 'secondary'> = {
  executed: 'success',
  partial: 'warning',
  rejected: 'warning',
  cancelled: 'secondary',
};

const OUTCOME_LABEL: Record<string, string> = {
  executed: 'Done',
  partial: 'Partly done',
  rejected: 'Not changed',
  cancelled: 'Cancelled',
};

/** What an action changed, kept with the turn that proposed it: status, each step and its field lines. */
function ActionsBlock({ actions }: { actions: AgentConversationAction[] }) {
  return (
    <div className="mt-2 space-y-2 border-t pt-2" data-testid="agent-actions">
      {actions.map((action) => (
        <div key={action.id} className="space-y-1">
          <Badge
            variant={OUTCOME_TONE[action.status] ?? 'secondary'}
            appearance="light"
            size="sm"
          >
            {OUTCOME_LABEL[action.status] ?? PROPOSAL_LABEL[action.status] ?? action.status}
          </Badge>
          {action.decided_by_name ? (
            <span className="ms-2 text-xs text-muted-foreground">
              {action.decided_by_name}
            </span>
          ) : null}
          <ul className="space-y-1">
            {action.steps.map((step, index) => (
              <li key={index} className="text-xs">
                <p className="break-words">{step.summary}</p>
                {step.error ? (
                  <p className="break-words text-destructive">{step.error}</p>
                ) : null}
                {(step.changes ?? []).map((change, i) => (
                  <p key={i} className="break-words text-muted-foreground">
                    {change.field}: {change.before} -&gt; {change.after}
                  </p>
                ))}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

const PROPOSAL_LABEL: Record<string, string> = {
  proposed: 'Waiting',
  expired: 'Expired',
};

function ActionOutcome({ outcome }: { outcome: AgentActionResponse }) {
  return (
    <Bubble role="agent">
      <div data-testid="agent-action-outcome">
        <Badge
          variant={OUTCOME_TONE[outcome.status] ?? 'secondary'}
          appearance="light"
          size="sm"
        >
          {OUTCOME_LABEL[outcome.status] ?? outcome.status}
        </Badge>
        <p className="mt-1.5 whitespace-pre-wrap break-words">
          {outcome.reply_text}
        </p>
      </div>
    </Bubble>
  );
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

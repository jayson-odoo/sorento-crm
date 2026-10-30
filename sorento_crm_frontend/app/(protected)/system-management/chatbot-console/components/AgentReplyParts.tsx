'use client';

import { useState } from 'react';
import { Check, Loader2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { getRespondContactsOutbound } from '../../respond-contacts/services/respondContactOutboundService';
import {
  AGENT_HIDDEN_TOOLS,
  AGENT_LIMIT_LABELS,
  agentToolLabel,
  type AgentActionResponse,
  type AgentConversationAction,
  type AgentPendingAction,
  type AgentReplyMeta,
  type AgentSteps,
} from '../types/agentConsole.types';

/** Pieces of a reply shared by the Agent and Auto tabs. */

export async function fetchContactOptions(
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

export function Bubble({
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
export function StepsDisclosure({ steps }: { steps: AgentSteps }) {
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

export function ReplyMeta({ meta }: { meta: AgentReplyMeta }) {
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
export function ProposalActions({
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
export function ActionsBlock({ actions }: { actions: AgentConversationAction[] }) {
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

export function ActionOutcome({ outcome }: { outcome: AgentActionResponse }) {
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


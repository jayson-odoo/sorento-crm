'use client';

import { useState } from 'react';
import { Check, Loader2, Undo2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { TakeoverCountdown } from '@/app/(protected)/sla-management/conversation-sla-tracking/components/TakeoverCountdown';
import {
  AGENT_HIDDEN_TOOLS,
  AGENT_LIMIT_LABELS,
  agentToolLabel,
  type AgentActionResponse,
  type AgentConversationAction,
  type AgentPendingAction,
  type AgentReasoning,
  type AgentReplyMeta,
  type AgentStepWaiting,
  type AgentSteps,
} from '../types/agentConsole.types';

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

type StepCall = AgentSteps['tool_calls'][number];

function callLine(call: StepCall): string {
  return call.detail
    ? call.detail
    : `${agentToolLabel(call.name)}: ${call.status} (${call.ms} ms)`;
}

/** One round's reasoning, collapsed until asked for. */
export function ReasoningItem({ label, text }: { label: string; text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <li data-testid="agent-reasoning">
      <button
        type="button"
        className="underline-offset-2 hover:underline"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {label}
      </button>
      {open ? (
        <p
          data-testid="agent-reasoning-text"
          className="mt-0.5 whitespace-pre-wrap break-words border-l-2 border-border pl-2"
        >
          {text}
        </p>
      ) : null}
    </li>
  );
}

/** Each round's thinking, then the tool calls of that round. */
function roundItems(calls: StepCall[], reasoning: AgentReasoning[]) {
  const last = Math.max(
    0,
    ...reasoning.map((r) => r.round),
    ...calls.map((c) => c.round ?? 1),
  );
  const items: React.ReactNode[] = [];
  for (let round = 1; round <= last; round += 1) {
    reasoning
      .filter((r) => r.round === round && !r.final)
      .forEach((r, index) =>
        items.push(
          <ReasoningItem
            key={`r${round}-${index}`}
            label={`Thinking (round ${round})`}
            text={r.text}
          />,
        ),
      );
    calls
      .filter((c) => (c.round ?? 1) === round)
      .forEach((c, index) =>
        items.push(<li key={`c${round}-${c.name}-${index}`}>{callLine(c)}</li>),
      );
    reasoning
      .filter((r) => r.round === round && r.final)
      .forEach((r, index) =>
        items.push(
          <ReasoningItem
            key={`f${round}-${index}`}
            label="Thinking (final answer)"
            text={r.text}
          />,
        ),
      );
  }
  return items;
}

/** The turn's steps, collapsed until asked for: rounds, tokens, each round's thinking and its tool calls. */
export function StepsDisclosure({ steps }: { steps: AgentSteps }) {
  const [open, setOpen] = useState(false);
  const calls = steps.tool_calls.filter((c) => !AGENT_HIDDEN_TOOLS.has(c.name));
  const reasoning = steps.reasoning ?? [];
  return (
    <div
      className="mt-1 break-words text-xs text-muted-foreground"
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
          {reasoning.length > 0
            ? roundItems(calls, reasoning)
            : calls.map((call, index) => (
                <li key={`${call.name}-${index}`}>{callLine(call)}</li>
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
          <Badge
            key={`${call.name}-${index}`}
            variant="secondary"
            size="sm"
            className="max-w-full"
            title={`${agentToolLabel(call.name)}: ${call.status}`}
          >
            <span className="truncate">
              {agentToolLabel(call.name)}: {call.status}
            </span>
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

/** A done change still waiting out its grace window: the screen's countdown and its Undo. */
export function WaitingStep({
  waiting,
  busy,
  onWithdraw,
  onExpire,
}: {
  waiting: AgentStepWaiting;
  busy: boolean;
  onWithdraw: () => void;
  onExpire: () => void;
}) {
  const [over, setOver] = useState(false);
  if (over) return null;
  return (
    <div
      className="mt-1 flex flex-col gap-1.5 sm:flex-row sm:items-center"
      data-testid="agent-step-waiting"
    >
      <TakeoverCountdown
        commitAt={waiting.commit_at}
        windowSeconds={waiting.window_seconds}
        onExpire={() => {
          setOver(true);
          onExpire();
        }}
        className="min-w-0 flex-1"
      />
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="w-fit shrink-0 gap-1.5"
        disabled={busy}
        onClick={onWithdraw}
      >
        <Undo2 className="size-3.5" />
        Undo
      </Button>
    </div>
  );
}

/** What an action changed, kept with the turn that proposed it: status, each step and its field lines. */
export function ActionsBlock({
  actions,
  withdrawing,
  onWithdraw,
  onExpire,
}: {
  actions: AgentConversationAction[];
  withdrawing: boolean;
  onWithdraw: (actionId: string, index: number) => void;
  onExpire: () => void;
}) {
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
                {step.waiting ? (
                  <WaitingStep
                    waiting={step.waiting}
                    busy={withdrawing}
                    onWithdraw={() => onWithdraw(action.id, index)}
                    onExpire={onExpire}
                  />
                ) : null}
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


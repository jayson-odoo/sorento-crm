'use client';

import { Badge } from '@/components/ui/badge';
import type {
  TurnDetailAgent,
  TurnDetailAgentContext,
  TurnDetailAgentRound,
  TurnDetailAgentTool,
} from '../types/chatbotTurn.types';

/**
 * An agent turn in the trace drawer (AGENT-PANEL-FIXES D): its model calls, the thinking it showed, its tool calls
 * and what it sent the model. Read off the `agent` block `trace_detail.py::_agent` composes.
 */

const num = (value: number | null | undefined) => (value ?? 0).toLocaleString('en-US');

const plural = (count: number | null | undefined, one: string, many: string) =>
  `${num(count)} ${count === 1 ? one : many}`;

// No UUIDs in the UI (repo rule): an id inside a note or an argument reads as [id].
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;
const maskIds = (text: string) => text.replace(UUID, '[id]');

/** The side calls a turn can make besides its rounds (`loop.py` `chat(kind=...)`). */
const CALL_WORDS: Record<string, string> = {
  dealer_access: 'Dealer access check',
  compaction: 'History summary',
  final: 'Final answer',
};

/** "Round N" counts the turn's rounds only; a side call is named for what it did. */
function callLabels(rounds: TurnDetailAgentRound[]): string[] {
  let n = 0;
  return rounds.map((round) => {
    const kind = round.kind_of_call ?? 'round';
    if (kind === 'round') {
      n += 1;
      return `Round ${n}`;
    }
    return CALL_WORDS[kind] ?? kind.replace(/_/g, ' ');
  });
}

const STOP_WORDS: Record<string, string> = { answer: 'Answered', text: 'Replied in text' };

function stopText(round: TurnDetailAgentRound): string {
  if (round.stop === 'tool_calls') {
    const called = (round.called ?? []).filter((name) => name !== 'plan');
    return called.length ? `Called ${called.join(', ')}` : 'Called a tool';
  }
  return round.stop ? (STOP_WORDS[round.stop] ?? round.stop) : '';
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

export function AgentRoundsSection({ agent }: { agent: TurnDetailAgent }) {
  if (agent.rounds.length === 0 && agent.failures.length === 0) return <Muted>No model call finished.</Muted>;
  const { totals } = agent;
  const labels = callLabels(agent.rounds);
  return (
    <div className="space-y-2 text-xs">
      <p className="text-muted-foreground tabular-nums">
        {totals.calls} {totals.calls === 1 ? 'call' : 'calls'}, {num(totals.ms)} ms, {num(totals.prompt_tokens)} in,{' '}
        {num(totals.completion_tokens)} out{totals.cached_tokens ? `, ${num(totals.cached_tokens)} cached` : ''}
      </p>
      <ol className="space-y-1.5">
        {agent.rounds.map((round, i) => (
          <li key={round.n} data-testid="agent-round" className="rounded-md border px-2 py-1.5">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="font-medium">{labels[i]}</span>
              <span className="min-w-0 truncate text-muted-foreground" title={round.model ?? ''}>
                {round.model ?? '-'}
              </span>
              <span className="tabular-nums">{num(round.ms)} ms</span>
              <span className="tabular-nums">{num(round.prompt_tokens)} in</span>
              <span className="tabular-nums">{num(round.completion_tokens)} out</span>
              {round.cached_tokens ? (
                <span className="tabular-nums text-muted-foreground">{num(round.cached_tokens)} cached</span>
              ) : null}
            </div>
            <div className="mt-0.5 flex flex-wrap gap-x-2 text-muted-foreground">
              {(round.kind_of_call ?? 'round') === 'round' && stopText(round) ? <span>{stopText(round)}</span> : null}
              {round.tools_offered ? (
                <span className="tabular-nums">
                  {plural(round.tools_offered, 'tool', 'tools')} offered ({num(round.tool_schema_chars)} chars)
                </span>
              ) : null}
              {round.message_chars != null ? (
                <span className="tabular-nums">messages {num(round.message_chars)} chars</span>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
      {agent.failures.map((failure, i) => (
        <p
          key={`failure-${i}`}
          className="rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-destructive"
        >
          A model call failed ({failure.error_class ?? 'unknown error'}).
        </p>
      ))}
    </div>
  );
}

export function AgentThinkingSection({ agent }: { agent: TurnDetailAgent }) {
  if (agent.reasoning.length === 0 && agent.plan.length === 0) return <Muted>The model showed no thinking.</Muted>;
  return (
    <div className="space-y-2 text-xs">
      {agent.plan.length > 0 ? (
        <div>
          <div className="mb-0.5 font-medium text-muted-foreground">Plan</div>
          <ol className="list-decimal space-y-0.5 pl-4">
            {agent.plan.map((part, i) => (
              <li key={i}>{part}</li>
            ))}
          </ol>
        </div>
      ) : null}
      {agent.reasoning.map((entry, i) => (
        <div key={i}>
          <div className="mb-0.5 font-medium text-muted-foreground">Round {entry.round ?? '-'}</div>
          <p className="whitespace-pre-wrap break-words">{entry.text}</p>
        </div>
      ))}
    </div>
  );
}

/** The call's arguments in one line; internal ids (`*_id`, `*_ids`) are left out, as the bot's "Looked up" does. */
function argsText(args: TurnDetailAgentTool['args']): string {
  if (!args) return '';
  return Object.entries(args)
    .filter(([key]) => !/_ids?$/.test(key))
    .map(([key, value]) => maskIds(`${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`))
    .join(', ');
}

export function AgentToolsSection({ agent }: { agent: TurnDetailAgent }) {
  if (agent.tools.length === 0) return <Muted>No tool was called.</Muted>;
  return (
    <ol className="space-y-1.5 text-xs">
      {agent.tools.map((tool, i) => {
        const ok = tool.status === 'ok' || tool.status === 'empty';
        const args = argsText(tool.args);
        return (
          <li key={i} data-testid="agent-tool" className="rounded-md border px-2 py-1.5">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="min-w-0 truncate font-medium" title={tool.name ?? ''}>
                {tool.name ?? '-'}
              </span>
              <Badge variant={ok ? 'success' : 'destructive'} appearance="light" size="sm">
                {tool.status ?? '-'}
              </Badge>
              <span className="tabular-nums">{num(tool.ms)} ms</span>
              {tool.rows != null ? <span className="tabular-nums">{plural(tool.rows, 'row', 'rows')}</span> : null}
              <span className="tabular-nums text-muted-foreground">{num(tool.result_chars)} chars</span>
              {tool.more ? <span className="text-muted-foreground">{num(tool.more)} not shown</span> : null}
            </div>
            {args ? (
              <p className="mt-0.5 break-words text-muted-foreground" title={args}>
                {args}
              </p>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function Note({ label, text, chars }: { label: string; text: string | null; chars: number | null }) {
  if (!text) return null;
  const cut = chars != null && chars > text.length;
  return (
    <div>
      <div className="mb-0.5 font-medium text-muted-foreground">
        {label} ({num(chars)} chars{cut ? ', first part shown' : ''})
      </div>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 p-2 text-2xs">
        {maskIds(text)}
      </pre>
    </div>
  );
}

export function AgentContextSection({ context }: { context: TurnDetailAgentContext | null }) {
  if (!context) return <Muted>This turn was recorded before the context was kept.</Muted>;
  const tools = context.tools ?? [];
  return (
    <div className="space-y-2 text-xs">
      <dl className="grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5">
        <dt className="text-muted-foreground">System prompt</dt>
        <dd>
          {context.prompt_key ?? '-'}
          {context.prompt_version != null ? ` v${context.prompt_version}` : ''} ({num(context.system_chars)} chars)
        </dd>
        <dt className="text-muted-foreground">History</dt>
        <dd>
          {plural(context.history_messages, 'message', 'messages')}
          {context.history_summary ? ' and a summary' : ''} (
          {num(context.history_chars)} chars)
        </dd>
        <dt className="text-muted-foreground">Tools</dt>
        <dd className="min-w-0 break-words" title={tools.join(', ')}>
          {plural(tools.length, 'tool', 'tools')} ({num(context.tool_schema_chars)} chars): {tools.join(', ')}
        </dd>
        {context.file_text_chars ? (
          <>
            <dt className="text-muted-foreground">Files</dt>
            <dd>{num(context.file_text_chars)} chars of file text</dd>
          </>
        ) : null}
        {context.images ? (
          <>
            <dt className="text-muted-foreground">Images</dt>
            <dd>{context.images}</dd>
          </>
        ) : null}
      </dl>
      <Note label="Before the history" text={context.context_before} chars={context.context_before_chars} />
      <Note label="Page and chat notes" text={context.context_after} chars={context.context_after_chars} />
    </div>
  );
}

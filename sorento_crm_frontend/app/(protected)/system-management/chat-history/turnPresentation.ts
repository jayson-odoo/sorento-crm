/**
 * Turning a `ChatbotTurn` into the words the Turn panel shows.
 *
 * Pure and separate from the component on purpose: this is where the wording decisions
 * live (AC-251's status words, AC-252's stage labels, AC-254's memory labels), and they
 * are the part a reviewer or the owner will want to argue with without reading JSX.
 *
 * What is NOT here: sentences. `summary` and `why` come from the engine already written
 * (D11), and the screen renders them verbatim. Anything in this file that produced prose
 * out of `facts` would be the frontend quietly inventing an account of what the bot did.
 */
import type {
  BranchKind,
  ChatbotTurn,
  TurnStage,
  TurnTraceRecord,
} from './types/chatbotTurn.types';
import { TURN_STAGES } from './types/chatbotTurn.types';

/** AC-252's row labels. The wire name is snake_case; nobody reads that in a timeline. */
const STAGE_LABELS: Record<TurnStage, string> = {
  received: 'Received',
  understood: 'Understood',
  access: 'Access',
  routed: 'Routed',
  looked_up: 'Looked up',
  replied: 'Replied',
  remembered: 'Remembered',
  sent: 'Sent',
};

/** Failure points that sit outside the eight-stage timeline. */
const OFF_TIMELINE_STAGE_LABELS: Record<string, string> = {
  intake: 'Intake',
  queued: 'Queue',
  casual_llm: 'Small talk',
};

export function stageLabel(stage: string): string {
  return (
    STAGE_LABELS[stage as TurnStage] ??
    OFF_TIMELINE_STAGE_LABELS[stage] ??
    stage.replace(/_/g, ' ')
  );
}

/** The lane, in words. Mirrors the engine's own `lane_words`. */
const LANE_WORDS: Record<BranchKind, string> = {
  access_denied: 'Access refused',
  escalate_offer: 'Escalation offer',
  out_of_scope: 'Escalation',
  ideate: 'Idea capture',
  offer_hold: 'Holding an offer open',
  escalation_declined: 'Escalation declined',
  check_promotion: 'Business query: promotion',
  low_signal: 'Small talk',
  clarify_menu: 'Asked to clarify',
  not_supported: 'Not supported',
  stock_denied: 'Stock access refused',
  demand_qty: 'Asked for a quantity',
  business_query: 'Business query',
};

export function laneWords(branchKind: BranchKind | null): string {
  if (!branchKind) return 'Lane not reached';
  return LANE_WORDS[branchKind] ?? branchKind.replace(/_/g, ' ');
}

export type TurnTone = 'ok' | 'failed' | 'pending';

export interface TurnHeadline {
  /** AC-251's status word. */
  word: string;
  tone: TurnTone;
}

/**
 * AC-251. The status word answers "what happened to this message?" in one glance, so it
 * is keyed on the LANE for a finished turn rather than on `status`, which only says
 * whether the machinery completed. "Done" would tell an operator nothing.
 */
export function turnHeadline(turn: ChatbotTurn): TurnHeadline {
  if (turn.status === 'failed') {
    return { word: `Failed at ${stageLabel(turn.stage ?? 'received')}`, tone: 'failed' };
  }
  if (turn.status === 'queued' || turn.status === 'processing') {
    return { word: 'Running', tone: 'pending' };
  }
  if (turn.status === 'delegated') return { word: 'In progress', tone: 'pending' };
  switch (turn.branch_kind) {
    case 'out_of_scope':
      return { word: 'Escalated', tone: 'ok' };
    case 'clarify_menu':
      return { word: 'Asked to clarify', tone: 'ok' };
    case 'demand_qty':
      return { word: 'Asked for a quantity', tone: 'ok' };
    case 'escalate_offer':
      return { word: 'Offered to escalate', tone: 'ok' };
    case 'escalation_declined':
      return { word: 'Escalation declined', tone: 'ok' };
    case 'access_denied':
    case 'stock_denied':
    case 'not_supported':
      return { word: 'Refused', tone: 'ok' };
    default:
      return { word: 'Answered', tone: 'ok' };
  }
}

/** Total wall time, from the turn's own timestamps, formatted the way latency already is. */
export function turnDuration(turn: ChatbotTurn): string | null {
  if (!turn.finished_at) return null;
  const ms = Date.parse(turn.finished_at) - Date.parse(turn.created_at);
  if (!Number.isFinite(ms) || ms < 0) return null;
  return formatMs(ms);
}

export function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/**
 * A short, copyable handle for one turn.
 *
 * NOT a bare UUID: the cursor rule is that a UUID never reaches the UI, and an operator
 * quoting a turn in a message needs something they can actually read back over the phone.
 * The full id stays available to copy.
 */
export function shortTurnId(id: string): string {
  return id.replace(/-/g, '').slice(0, 4);
}

export type TimelineRow =
  | { kind: 'stage'; record: TurnTraceRecord; label: string }
  | { kind: 'not-reached'; labels: string[] };

/**
 * AC-252, and the one place the mockup and the AC had to be reconciled.
 *
 * The AC says a stage that did not run is "omitted, not greyed", and the mockup collapses
 * them into a single "skipped / not reached" row. Both are answers to the same thing -
 * eight greyed placeholders on a turn that failed at stage two is noise - and the mockup's
 * is the better one, because on a FAILED turn "Routed, Looked up, Replied and Remembered
 * did not run" is information the operator needs. So: never a greyed row per stage, and
 * one collapsed row naming the rest, only when the turn stopped early.
 *
 * A lane that legitimately has no `looked_up` (a clarify ask never looks anything up) is a
 * different case: those stages are absent from the trace and stay absent here, with no
 * "not reached" row, because nothing about them went wrong.
 */
export function buildTimeline(turn: ChatbotTurn): TimelineRow[] {
  const rows: TimelineRow[] = [];
  const present = new Set(turn.trace.map((r) => r.stage));

  for (const record of turn.trace) {
    rows.push({ kind: 'stage', record, label: stageLabel(record.stage) });
  }

  if (turn.status !== 'failed') return rows;

  // Everything between the failed stage and the last stage that DID run. `sent` usually
  // still runs on a failed turn (the customer gets the error reply), so the collapsed row
  // belongs in the middle, not at the end.
  const failedAt = turn.trace.findIndex((r) => r.status === 'failed');
  if (failedAt === -1) return rows;
  const failedStage = turn.trace[failedAt].stage;
  const notReached = TURN_STAGES.filter(
    (stage) =>
      TURN_STAGES.indexOf(stage) > TURN_STAGES.indexOf(failedStage) && !present.has(stage),
  );
  if (notReached.length === 0) return rows;

  const insertAt = rows.findIndex(
    (row) => row.kind === 'stage' && row.record.status === 'failed',
  );
  rows.splice(insertAt + 1, 0, {
    kind: 'not-reached',
    labels: notReached.map(stageLabel),
  });
  return rows;
}

export type MemoryChangeKind = 'kept' | 'new' | 'cleared';

export interface MemoryChip {
  kind: MemoryChangeKind;
  /** What an operator reads. */
  label: string;
  /** The session-vars key behind it, for the tooltip (AC-254). */
  rawKey: string;
}

/** Session-var keys in words. Anything unmapped falls back to its own key, humanised. */
const MEMORY_LABELS: Record<string, string> = {
  entities: 'things being asked about',
  domain_hint: 'topic',
  intent_hint: 'what they want',
  access_levels: 'price tier',
  query_brands: 'brand',
  last_result_set: 'the list last shown',
  selection_context: 'what a number would mean',
  dym_offer: 'did-you-mean offer',
  dym_last_result_set: 'did-you-mean suggestions',
  routing: 'team and agent',
  escalation: 'escalation state',
  response: 'the last reply',
  pending: 'what the bot is waiting for',
  tier_menu: 'the tier menu',
  date_filter_start: 'date from',
  date_filter_end: 'date to',
  requested_attributes: 'which details were asked for',
  ideation: 'idea draft',
};

export function memoryLabel(key: string): string {
  return MEMORY_LABELS[key] ?? key.replace(/_/g, ' ');
}

/**
 * AC-254. Kept / New / Cleared, derived from the Remembered stage's `raw.before` and
 * `raw.after`.
 *
 * Returns an empty list rather than guessing when the stage did not record both sides:
 * a memory panel that shows a confident "nothing changed" for a turn whose trace simply
 * did not carry `before` would be worse than showing nothing.
 */
export function memoryChips(record: TurnTraceRecord | undefined): MemoryChip[] {
  if (!record) return [];
  const raw = record.raw as { before?: Record<string, unknown>; after?: Record<string, unknown> } | null;
  const after = raw && typeof raw === 'object' ? raw.after : undefined;
  if (!after || typeof after !== 'object') return [];
  const before = raw && typeof raw === 'object' && raw.before && typeof raw.before === 'object'
    ? raw.before
    : {};

  const chips: MemoryChip[] = [];
  const isSet = (value: unknown) =>
    value !== null && value !== undefined && !(Array.isArray(value) && value.length === 0);

  for (const key of Object.keys(after)) {
    if (!isSet(after[key])) continue;
    chips.push({
      kind: isSet(before[key]) ? 'kept' : 'new',
      label: memoryLabel(key),
      rawKey: key,
    });
  }
  for (const key of Object.keys(before)) {
    if (isSet(before[key]) && !isSet(after[key])) {
      chips.push({ kind: 'cleared', label: memoryLabel(key), rawKey: key });
    }
  }
  const order: Record<MemoryChangeKind, number> = { kept: 0, new: 1, cleared: 2 };
  return chips.sort((a, b) => order[a.kind] - order[b.kind] || a.label.localeCompare(b.label));
}

/** The Remembered record, when the turn got that far. */
export function rememberedRecord(turn: ChatbotTurn): TurnTraceRecord | undefined {
  return turn.trace.find((r) => r.stage === 'remembered');
}

/** AC-253: manual retry is the only retry, and only from a failed turn (R4). */
export function canRetry(turn: ChatbotTurn): boolean {
  return turn.status === 'failed';
}

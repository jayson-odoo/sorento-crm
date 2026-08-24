/**
 * Client-side derivation of the state-transition summary, mirroring the SQL view
 * `public.v_turn_state_transition` so the transcript shows the same answer psql does:
 * which entities a turn lost/gained, which decision flags fired, and whether
 * post-processing overruled the LLM.
 *
 * Kept deliberately in lockstep with the view (see migration 295). If the view's
 * identity rule (N2), flag domain (N3) or wrapping (N1) change, change both together.
 */
import type { StateTrace } from './types/chatHistory.types';

interface Entity {
  /** Identity for lost/gained set arithmetic: lower(trim(raw)). */
  key: string;
  /** Display label, original casing preserved: "etype:raw". */
  display: string;
}

export interface StateSummary {
  /** false when the turn wrote no state (`after: null`) - set arithmetic is suppressed. */
  wroteState: boolean;
  /** Entities present BEFORE but absent AFTER. null (not []) when !wroteState. */
  entitiesLost: string[] | null;
  /** Entities present AFTER but absent BEFORE. null (not []) when !wroteState. */
  entitiesGained: string[] | null;
  /** Decision flags that fired this turn: booleans set-when-true, source=<value>. */
  causeFlags: string[];
  /** How post-processing diverged from the raw LLM. null when parser_raw absent. */
  parserDrift: string[] | null;
  traceVersion: string;
}

function asArray(v: unknown): Record<string, unknown>[] {
  return Array.isArray(v) ? (v as Record<string, unknown>[]) : [];
}

function entitiesFrom(layer: unknown): Entity[] {
  if (!layer || typeof layer !== 'object') return [];
  const raw = (layer as Record<string, unknown>).entities;
  const out: Entity[] = [];
  for (const e of asArray(raw)) {
    const rawTok = e.raw;
    if (rawTok == null) continue;
    const label = String(rawTok);
    const etype = String(e.entity_type ?? e.hint ?? '?');
    out.push({ key: label.trim().toLowerCase(), display: `${etype}:${label}` });
  }
  return out;
}

/** true only when the layer is a real object - a present-but-null `after` is false. */
function isObject(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === 'object' && !Array.isArray(v);
}

function truthyFlag(applied: Record<string, unknown> | null | undefined, key: string): boolean {
  // Match the view: (papp->>key)::text = 'true' - the stringified value equals "true".
  return applied != null && String(applied[key]) === 'true';
}

/** Sorted set difference by key; display label of the `from` side is what's reported. */
function diffByKey(from: Entity[], against: Entity[]): string[] {
  const other = new Set(against.map((e) => e.key));
  const seen = new Set<string>();
  const out: string[] = [];
  for (const e of from) {
    if (other.has(e.key) || seen.has(e.display)) continue;
    seen.add(e.display);
    out.push(e.display);
  }
  return out.sort();
}

export function deriveStateSummary(trace: StateTrace | null | undefined): StateSummary | null {
  if (!trace || typeof trace !== 'object') return null;

  const wroteState = isObject(trace.after);
  const before = entitiesFrom(trace.before);
  const after = entitiesFrom(trace.after);
  const papp = isObject(trace.parser_applied) ? trace.parser_applied : null;
  const praw = trace.parser_raw;

  const causeFlags: string[] = [];
  for (const f of [
    'scope_exclusive_applied',
    'entity_op_applied',
    'entities_filtered',
    'dym_pick_applied',
  ]) {
    if (truthyFlag(papp, f)) causeFlags.push(f);
  }
  const source = papp?.domain_signal_source;
  if (source != null) causeFlags.push(`source=${String(source)}`);
  causeFlags.sort();

  let parserDrift: string[] | null = null;
  if (isObject(praw)) {
    const drift: string[] = [];
    if ((praw.domain_hint ?? null) !== (papp?.domain_hint ?? null)) drift.push('domain');
    if ((praw.scope_exclusive ?? null) !== (papp?.scope_exclusive ?? null)) drift.push('scope');
    if (JSON.stringify(praw.entities ?? []) !== JSON.stringify(papp?.entities ?? [])) {
      drift.push('entities');
    }
    parserDrift = drift.sort();
  }

  return {
    wroteState,
    entitiesLost: wroteState ? diffByKey(before, after) : null,
    entitiesGained: wroteState ? diffByKey(after, before) : null,
    causeFlags,
    parserDrift,
    traceVersion: trace.v != null ? String(trace.v) : '?',
  };
}

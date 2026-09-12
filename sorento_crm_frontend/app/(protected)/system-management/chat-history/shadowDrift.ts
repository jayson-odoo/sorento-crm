/**
 * Shadow parse vs live parse, said in the fewest words that are still true (AC-1029,
 * AC-1030).
 *
 * A shadow row is a second parse of a live turn, run under the version named by
 * `system_settings.chatbot_parser_shadow_version`. The owner watches the window in the
 * console and promotes by hand, so the only question these helpers answer is "did this
 * turn come out differently, and how often does that happen".
 *
 * Pure, and deliberately outside the components: the rule for what counts as drift is the
 * thing a reviewer argues with, and it should be readable without a render tree around it.
 */
import type { StateTrace } from './types/chatHistory.types';
import type { ChatbotTurn, ShadowTurnLiveSide, ShadowTurnSummary } from './types/chatbotTurn.types';

/** The axes a shadow parse can differ on. Ordered, so the badge reads the same every time. */
export const DRIFT_AXES = ['branch', 'domains'] as const;
export type DriftAxis = (typeof DRIFT_AXES)[number];

function sameDomains(live: string[], shadow: string[]): boolean {
  // ORDER MATTERS: the sections of a fan-out answer are rendered in the order the dealer
  // said the domains (D11), so a parse that names the same two the other way round is a
  // different answer and drift is the honest word for it.
  return live.length === shadow.length && live.every((d, i) => d === shadow[i]);
}

/**
 * Which axes this shadow row disagrees with its live row about. `[]` means the two agree.
 *
 * An UNKNOWN side is not a difference. `branch_kind` is null on a turn that failed before
 * routing and `domains` is null on a parse that predates v3; counting either as drift
 * would fill the window with rows that say nothing about the new prompt.
 */
export function driftAxes(
  live: ChatbotTurn | ShadowTurnLiveSide | null | undefined,
  shadow: ChatbotTurn,
): DriftAxis[] {
  if (!live) return [];
  const axes: DriftAxis[] = [];
  if (live.branch_kind != null && shadow.branch_kind != null && live.branch_kind !== shadow.branch_kind) {
    axes.push('branch');
  }
  if (live.domains != null && shadow.domains != null && !sameDomains(live.domains, shadow.domains)) {
    axes.push('domains');
  }
  return axes;
}

/**
 * The same rule for a CROSS-CONTACT row, where the live side rides the shadow row itself
 * (`live`) instead of coming from a map of the conversation's own turns. One rule, two
 * callers: a grid that judged drift differently from the drawer would be worse than no
 * grid.
 */
export function rowDrift(shadow: ChatbotTurn): DriftAxis[] {
  return driftAxes(shadow.live, shadow);
}

/** The drifted axes per live `message_id`, for every shadow row that has a live row. */
export function driftByMessageId(
  shadowTurns: ChatbotTurn[],
  liveByMessageId: Map<string, ChatbotTurn>,
): Map<string, DriftAxis[]> {
  const out = new Map<string, DriftAxis[]>();
  for (const shadow of shadowTurns) {
    const messageId = shadow.shadow_of ?? shadow.message_id;
    if (!messageId) continue;
    out.set(messageId, driftAxes(liveByMessageId.get(messageId), shadow));
  }
  return out;
}

/** The shadow row per live `message_id`, so a panel can show both parses side by side. */
export function shadowByMessageId(shadowTurns: ChatbotTurn[]): Map<string, ChatbotTurn> {
  const out = new Map<string, ChatbotTurn>();
  for (const shadow of shadowTurns) {
    const messageId = shadow.shadow_of ?? shadow.message_id;
    // Newest first from the endpoint, and a re-run of the same window writes a second
    // shadow row: the first one seen is the newest, which is the one to compare.
    if (messageId && !out.has(messageId)) out.set(messageId, shadow);
  }
  return out;
}

function percent(fraction: number | null): string | null {
  return fraction == null ? null : `${Math.round(fraction * 100)}%`;
}

/**
 * AC-1030's one line: how many shadow turns the range holds and how often the two parses
 * agreed. Null when there is nothing to say, so the header renders nothing rather than a
 * line of zeroes.
 */
export function shadowSummaryLine(summary: ShadowTurnSummary | null | undefined): string | null {
  if (!summary || summary.count === 0) return null;
  const branch = percent(summary.branch_parity);
  const asks = percent(summary.asks_parity);
  const parts = [`${summary.count} shadow ${summary.count === 1 ? 'turn' : 'turns'}`];
  // "not measured" rather than 0%: a range where no pair could be compared and a range
  // where none of them matched are opposite findings.
  parts.push(`branch parity ${branch ?? 'not measured'}`);
  parts.push(`asks parity ${asks ?? 'not measured'}`);
  return parts.join(' · ');
}

/**
 * A turn's parse in the shape `deriveStateSummary` already reads, so the shadow side of
 * the Parser drift row is derived by the SAME function as the live side.
 *
 * The `understood` stage record carries `raw: {parser_raw, derived}` - what the model
 * emitted and what post-processing made of it, which is exactly the pair that row
 * compares. `before` / `after` are left out on purpose: a shadow turn writes no session,
 * so it has no entity movement to report and an invented empty one would read as "it lost
 * everything".
 */
export function parseStateTrace(turn: ChatbotTurn | undefined): StateTrace | null {
  if (!turn) return null;
  const understood = turn.trace.find((record) => record.kind == null && record.stage === 'understood');
  const raw = understood?.raw as { parser_raw?: unknown; derived?: unknown } | undefined;
  if (!raw || typeof raw !== 'object') return null;
  return {
    v: 'shadow',
    before: null,
    after: null,
    parser_raw: (raw.parser_raw ?? null) as Record<string, unknown> | null,
    parser_applied: (raw.derived ?? null) as Record<string, unknown> | null,
  };
}

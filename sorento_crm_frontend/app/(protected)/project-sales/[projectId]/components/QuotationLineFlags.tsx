'use client';

import * as React from 'react';
import { TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useCachedLineVerdicts, useLineVerdict } from '../../_shared/hooks/useProjects';
import type {
  QuotationLine,
  QuotationLineVerdict,
} from '../../_shared/types/project.types';
import { isSectionDraft, type LineDraft } from './quotationLineDraft';

const FLOOR_LEVEL_LABELS: Record<string, string> = {
  product: 'this product',
  category: 'its category',
  category_ancestor: 'a parent category',
  system: 'the company default',
  series: 'the series',
};

/** The three fields a draft is judged by, as the verdict is asked for them. */
function verdictDraft(draft: LineDraft) {
  const productId = (draft.product_id ?? '').trim();
  const setId = (draft.product_set_id ?? '').trim();
  const price = (draft.unit_price ?? '').trim();
  return {
    product_id: productId || undefined,
    product_set_id: setId || undefined,
    unit_price: price || undefined,
  };
}

/** The draft still says what the saved row says, so the saved row's flags answer for it. */
function isPristine(line: QuotationLine | null, draft: LineDraft): line is QuotationLine {
  const asked = verdictDraft(draft);
  return (
    line != null &&
    (line.product_id ?? '') === (asked.product_id ?? '') &&
    (line.product_set_id ?? '') === (asked.product_set_id ?? '') &&
    (asked.unit_price ?? '') === (line.unit_price ?? '')
  );
}

export interface LineFacts {
  nonStandard: boolean;
  belowFloor: boolean;
  /** NON-CANCELLABLE-ITEMS F1: the badge under the description, by the same rule as the rest. */
  nonCancellable: boolean;
}

/**
 * What is true about one line, from the saved row while the draft matches it and from the live
 * verdict once it diverges. The one rule the pills AND the lines filter read
 * (PROJECT-QUOTE-LINE-TOOLS), so a filter can never disagree with the pill on the row.
 */
export function lineFacts(
  line: QuotationLine | null,
  draft: LineDraft,
  verdict: QuotationLineVerdict | null | undefined,
): LineFacts {
  const asked = verdictDraft(draft);
  const linked = Boolean(asked.product_id || asked.product_set_id);
  if (isSectionDraft(draft)) return NO_FACTS;
  if (isPristine(line, draft)) return storedLineFacts(line);
  const belowFloor = Boolean(verdict?.is_below_floor);
  const nonStandard = linked && Boolean(verdict?.is_non_standard);
  const nonCancellable = linked && Boolean(verdict?.is_non_cancellable);
  return { nonStandard, belowFloor, nonCancellable };
}

/** A heading, or a line with nothing to judge: no flag of any kind. */
const NO_FACTS: LineFacts = {
  nonStandard: false,
  belowFloor: false,
  nonCancellable: false,
};

/** A saved line's facts, off its stored flags: the ones the approval banner counts. */
export function storedLineFacts(line: QuotationLine): LineFacts {
  if (line.is_section) return NO_FACTS;
  const linked = Boolean(line.product_id || line.product_set_id);
  return {
    nonStandard: linked && Boolean(line.is_non_standard),
    belowFloor: Boolean(line.is_below_floor),
    nonCancellable: linked && Boolean(line.is_non_cancellable),
  };
}

/**
 * What is true about the line, ON THE SPOT (the client: "cannot wait until I save").
 *
 * **Non-standard** means the linked product or set is outside the series (the server's). **Minimum price** is the server's too: while the
 * draft matches the saved row the saved verdicts show, and the moment it diverges the server is
 * asked (debounced, via `useLineVerdict`) with the same functions the save runs. There is no
 * "Below default price" pill (owner, 12 Nov 2026: the minimum price pill is enough).
 *
 * Two cells read it (owner meeting, 29 Oct): Non-standard stays in the Product cell, the floor
 * sits under the price in the Rate cell and reads "Below minimum price". Both ask the same query
 * key, so React Query asks the server once.
 */
function useLineFacts(
  quotationId: string | null,
  seriesId: string | null | undefined,
  line: QuotationLine | null,
  draft: LineDraft,
  savedSeriesId?: string | null,
) {
  const asked = verdictDraft(draft);
  // A saved row's flags were judged against the SAVED series: once the editor's series moves
  // (picked, changed or cleared), the row is judged afresh like any changed draft (F1).
  const pristine = isPristine(line, draft) && !seriesMoved(seriesId, savedSeriesId);
  // A new scope has no quotation id yet: it is judged against the series the editor holds
  // (PRICING-UX-FIXES A), so the alerts are live before the first save too.
  const verdict = useLineVerdict(
    { quotationId, seriesId },
    asked,
    !pristine && Boolean(asked.product_id || asked.product_set_id),
  );
  const facts = pristine
    ? lineFacts(line, draft, verdict.data)
    : lineFacts(null, draft, verdict.data);
  const floor = pristine
    ? describeFloor(line)
    : describeVerdictFloor(verdict.data ?? null);

  return { ...facts, floor };
}

/** The editor's series is not the one the saved rows were judged against. */
function seriesMoved(
  seriesId: string | null | undefined,
  savedSeriesId: string | null | undefined,
): boolean {
  if (seriesId === undefined || savedSeriesId === undefined) return false;
  return (seriesId || null) !== (savedSeriesId || null);
}

/**
 * Every line's facts at once, for the lines filter and its counts. It READS the verdicts the rows'
 * own pills ask for (`useCachedLineVerdicts`, same cache key, never fetching itself), so filtering
 * costs no request. While a changed draft waits on its verdict the row keeps its last known facts,
 * exactly as its pill keeps the previous verdict on screen (`keepPreviousData`), so a row being
 * typed into is not hidden by the filter on the first keystroke.
 */
export function useLinesFacts(
  target: { quotationId: string | null; seriesId?: string | null; savedSeriesId?: string | null },
  lines: { key: string; line: QuotationLine | null; draft: LineDraft }[],
): Map<string, LineFacts> {
  const moved = seriesMoved(target.seriesId, target.savedSeriesId);
  const verdicts = useCachedLineVerdicts(
    { quotationId: target.quotationId, seriesId: target.seriesId },
    lines.map((row) => verdictDraft(row.draft)),
  );
  const lastKnown = React.useRef(new Map<string, LineFacts>());
  return React.useMemo(() => {
    const facts = new Map<string, LineFacts>();
    lines.forEach((row, index) => {
      if (isSectionDraft(row.draft)) {
        facts.set(row.key, NO_FACTS);
        return;
      }
      const verdict = verdicts[index];
      const asked = verdictDraft(row.draft);
      // A series move re-judges saved rows too, as their pills do (`useLineFacts`).
      const line = moved ? null : row.line;
      // A row naming no product or set is never judged, so it is not waiting on anything.
      const waiting =
        verdict === undefined &&
        Boolean(asked.product_id || asked.product_set_id) &&
        !isPristine(line, row.draft);
      const known = lastKnown.current.get(row.key);
      const fact = waiting && known ? known : lineFacts(line, row.draft, verdict ?? null);
      lastKnown.current.set(row.key, fact);
      facts.set(row.key, fact);
    });
    return facts;
  }, [lines, verdicts, moved]);
}

/** The Product cell's flag: Non-standard. */
export function LineFlags({
  quotationId,
  seriesId,
  savedSeriesId,
  line,
  draft,
}: {
  /** Null on a scope not saved yet: the verdict is then asked by `seriesId`. */
  quotationId: string | null;
  /** The series the editor is quoting from (null for none); undefined asks by quotation. */
  seriesId?: string | null;
  /** The series the saved rows were judged against; a different editor series re-judges them. */
  savedSeriesId?: string | null;
  line: QuotationLine | null;
  draft: LineDraft;
}) {
  const { nonStandard } = useLineFacts(quotationId, seriesId, line, draft, savedSeriesId);
  if (!nonStandard) return null;

  return (
    <div className="flex flex-wrap items-center gap-1">
      <Badge
        variant="secondary"
        // Wraps in the narrow Product column instead of spilling into the next cell, as the
        // Below minimum price pill does.
        className="h-auto max-w-full gap-1 whitespace-normal py-0.5 text-start text-2xs leading-tight"
        title="Outside the series this scope is quoted from"
      >
        <TriangleAlert className="size-3" aria-hidden />
        Non-standard
      </Badge>
    </div>
  );
}

/**
 * NON-CANCELLABLE-ITEMS F1 (owner hand test, 12 Nov): the badge under the description, live like
 * Non-standard: the same `useLineFacts` (saved row while nothing moved, the line verdict the
 * moment the item, the series or the price does), so it appears without a save or a reload.
 */
export function NonCancellableFlag({
  quotationId,
  seriesId,
  savedSeriesId,
  line,
  draft,
}: {
  quotationId: string | null;
  seriesId?: string | null;
  savedSeriesId?: string | null;
  line: QuotationLine | null;
  draft: LineDraft;
}) {
  const { nonCancellable } = useLineFacts(quotationId, seriesId, line, draft, savedSeriesId);
  if (!nonCancellable) return null;
  return (
    <div className="mt-1">
      <Badge variant="warning" appearance="light" size="sm" className="whitespace-nowrap">
        Non-cancellable
      </Badge>
    </div>
  );
}

/**
 * The Rate cell's flag, under the price: "Below minimum price", no amount. Where the floor was set is the
 * badge's tooltip only; the owner removed the printed "Set on ..." line (1 Nov 2026).
 */
export function MinimumPriceFlag({
  quotationId,
  seriesId,
  savedSeriesId,
  line,
  draft,
}: {
  quotationId: string | null;
  seriesId?: string | null;
  savedSeriesId?: string | null;
  line: QuotationLine | null;
  draft: LineDraft;
}) {
  const { belowFloor, floor } = useLineFacts(quotationId, seriesId, line, draft, savedSeriesId);
  if (!belowFloor) return null;

  return (
    <div className="mt-1 text-end">
      <MinimumPriceBadge title={floor.source} />
    </div>
  );
}

/**
 * The "Below minimum price" pill itself. The Flags filter's own words, and no amount (owner hand
 * test, 11 Nov: "just don't show the minimum price in the warning"); where the floor was set
 * stays the tooltip.
 */
export function MinimumPriceBadge({ title }: { title?: string }) {
  return (
    // No icon and tight padding, on one line: the Rate cell is narrow.
    <Badge
      variant="destructive"
      className="h-auto whitespace-nowrap rounded-md px-1.5 py-0.5 text-2xs leading-tight"
      title={title}
    >
      Below minimum price
    </Badge>
  );
}

/** Where the floor was set: the pill's tooltip. The amount itself is not shown (owner, 11 Nov). */
type FloorFacts = { source: string };

const NO_FLOOR_VALUE = 'Below the minimum price for this item.';

function describeVerdictFloor(verdict: QuotationLineVerdict | null): FloorFacts {
  if (!verdict?.floor_value) return { source: NO_FLOOR_VALUE };
  const level = verdict.floor_level
    ? (FLOOR_LEVEL_LABELS[verdict.floor_level] ?? verdict.floor_level)
    : 'this item';
  return { source: `Set on ${level}.` };
}

/** Says which rule bit, so the salesperson knows whose policy to argue with. */
function describeFloor(line: QuotationLine): FloorFacts {
  if (!line.floor_value_applied) return { source: NO_FLOOR_VALUE };
  const level = line.floor_level_applied
    ? (FLOOR_LEVEL_LABELS[line.floor_level_applied] ?? line.floor_level_applied)
    : 'policy';
  return { source: `Set on ${level}.` };
}

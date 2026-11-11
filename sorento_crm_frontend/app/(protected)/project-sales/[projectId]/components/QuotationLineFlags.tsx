'use client';

import * as React from 'react';
import { TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useQueries } from '@tanstack/react-query';
import { lineVerdictKey, useLineVerdict } from '../../_shared/hooks/useProjects';
import type {
  QuotationLine,
  QuotationLineVerdict,
} from '../../_shared/types/project.types';
import { formatMyr } from './QuotationsPanel';
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
  /**
   * Below the default price but NOT below the minimum price: the approval banner's "priced below
   * the default price" clause exactly (`reasons_text`, discounted minus below floor). A line below
   * the minimum price carries the Minimum price pill and the banner's other clause instead.
   */
  belowDefault: boolean;
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
  if (isPristine(line, draft)) return storedLineFacts(line);
  const belowFloor = Boolean(verdict?.is_below_floor);
  const nonStandard = linked && Boolean(verdict?.is_non_standard);
  const discounted = linked && Boolean(verdict?.is_discounted);
  return { nonStandard, belowFloor, belowDefault: discounted && !belowFloor };
}

/** A saved line's facts, off its stored flags: the ones the approval banner counts. */
export function storedLineFacts(line: QuotationLine): LineFacts {
  if (line.is_section) return { nonStandard: false, belowFloor: false, belowDefault: false };
  const linked = Boolean(line.product_id || line.product_set_id);
  const belowFloor = Boolean(line.is_below_floor);
  return {
    nonStandard: linked && Boolean(line.is_non_standard),
    belowFloor,
    belowDefault: linked && Boolean(line.is_discounted) && !belowFloor,
  };
}

/**
 * What is true about the line, ON THE SPOT (the client: "cannot wait until I save").
 *
 * **Non-standard** means the linked product or set is outside the series (the server's). **Minimum price** is the server's too: while the
 * draft matches the saved row the saved verdicts show, and the moment it diverges the server is
 * asked (debounced, via `useLineVerdict`) with the same functions the save runs. **Below default
 * price** is judged the same way, by the save's default-price rule.
 *
 * Two cells read it (owner meeting, 29 Oct): Non-standard stays in the Product cell, the floor
 * sits under the price in the Rate cell and reads "Minimum price RM x". Both ask the same query
 * key, so React Query asks the server once.
 */
function useLineFacts(
  quotationId: string | null,
  seriesId: string | null | undefined,
  line: QuotationLine | null,
  draft: LineDraft,
) {
  const asked = verdictDraft(draft);
  const pristine = isPristine(line, draft);
  // A new scope has no quotation id yet: it is judged against the series the editor holds
  // (PRICING-UX-FIXES A), so the alerts are live before the first save too.
  const verdict = useLineVerdict(
    { quotationId, seriesId },
    asked,
    !pristine && Boolean(asked.product_id || asked.product_set_id),
  );
  const facts = lineFacts(line, draft, verdict.data);
  const floor = pristine
    ? describeFloor(line)
    : describeVerdictFloor(verdict.data ?? null);

  return { ...facts, floor };
}

/**
 * Every line's facts at once, for the lines filter and its counts. It only READS the verdicts the
 * rows' own pills ask for (same cache key, never fetching itself), so filtering costs no request
 * and cannot answer differently from the pill on the row.
 */
export function useLinesFacts(
  target: { quotationId: string | null; seriesId?: string | null },
  lines: { key: string; line: QuotationLine | null; draft: LineDraft }[],
): Map<string, LineFacts> {
  // One observer per DISTINCT draft: a duplicated line asks exactly what its source asks.
  const keys = lines.map((row) => lineVerdictKey(target, verdictDraft(row.draft)));
  const distinct = Array.from(new Map(keys.map((key) => [JSON.stringify(key), key])).values());
  const verdicts = useQueries({
    queries: distinct.map((queryKey) => ({
      queryKey,
      queryFn: (): Promise<QuotationLineVerdict | null> => Promise.resolve(null),
      enabled: false,
    })),
  });
  const answers = verdicts.map((query) => query.data);
  return React.useMemo(() => {
    const byKey = new Map(
      distinct.map((key, index) => [JSON.stringify(key), answers[index] ?? null]),
    );
    return new Map(
      lines.map((row, index) => [
        row.key,
        isSectionDraft(row.draft)
          ? { nonStandard: false, belowFloor: false, belowDefault: false }
          : lineFacts(row.line, row.draft, byKey.get(JSON.stringify(keys[index])) ?? null),
      ]),
    );
    // `verdicts` is a fresh array every render; its answers are what matter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines, target.quotationId, target.seriesId, ...answers]);
}

/** The Product cell's flags: Non-standard and Below default price, each once. */
export function LineFlags({
  quotationId,
  seriesId,
  line,
  draft,
}: {
  /** Null on a scope not saved yet: the verdict is then asked by `seriesId`. */
  quotationId: string | null;
  /** The series the editor is quoting from (null for none); undefined asks by quotation. */
  seriesId?: string | null;
  line: QuotationLine | null;
  draft: LineDraft;
}) {
  const { nonStandard, belowDefault } = useLineFacts(quotationId, seriesId, line, draft);
  if (!nonStandard && !belowDefault) return null;

  return (
    <div className="flex flex-wrap items-center gap-1">
      {nonStandard && (
        <Badge
          variant="secondary"
          className="gap-1 text-2xs"
          title="Outside the series this scope is quoted from"
        >
          <TriangleAlert className="size-3" aria-hidden />
          Non-standard
        </Badge>
      )}
      {/* The approval banner's own words, so the pill and the banner name one fact. */}
      {belowDefault && (
        <Badge
          variant="secondary"
          className="gap-1 text-2xs"
          title="Priced below the default price: this quotation needs a manager's approval"
        >
          <TriangleAlert className="size-3" aria-hidden />
          Below default price
        </Badge>
      )}
    </div>
  );
}

/**
 * The Rate cell's flag, under the price: "Minimum price RM x". Where the floor was set is the
 * badge's tooltip only; the owner removed the printed "Set on ..." line (1 Nov 2026).
 */
export function MinimumPriceFlag({
  quotationId,
  seriesId,
  line,
  draft,
}: {
  quotationId: string | null;
  seriesId?: string | null;
  line: QuotationLine | null;
  draft: LineDraft;
}) {
  const { belowFloor, floor } = useLineFacts(quotationId, seriesId, line, draft);
  if (!belowFloor) return null;

  return (
    <div className="mt-1 text-end">
      <MinimumPriceBadge value={floor.value} title={floor.source} />
    </div>
  );
}

/** The "Minimum price RM x" pill itself, shared with a customer's suggested price in review. */
export function MinimumPriceBadge({ value, title }: { value: string | null; title?: string }) {
  return (
    // No icon and tight padding: the Rate cell is narrow, and "Minimum" must fit on a line.
    <Badge
      variant="destructive"
      className="h-auto whitespace-normal rounded-md px-1.5 py-0.5 text-start text-2xs leading-tight"
      title={title}
    >
      {value ? `Minimum price ${formatMyr(value)}` : 'Minimum price'}
    </Badge>
  );
}

type FloorFacts = { value: string | null; source: string };

const NO_FLOOR_VALUE = 'Below the minimum price for this item.';

function describeVerdictFloor(verdict: QuotationLineVerdict | null): FloorFacts {
  if (!verdict?.floor_value) return { value: null, source: NO_FLOOR_VALUE };
  const level = verdict.floor_level
    ? (FLOOR_LEVEL_LABELS[verdict.floor_level] ?? verdict.floor_level)
    : 'this item';
  return { value: verdict.floor_value, source: `Set on ${level}.` };
}

/** Says which rule bit, so the salesperson knows whose policy to argue with. */
function describeFloor(line: QuotationLine): FloorFacts {
  if (!line.floor_value_applied) return { value: null, source: NO_FLOOR_VALUE };
  const level = line.floor_level_applied
    ? (FLOOR_LEVEL_LABELS[line.floor_level_applied] ?? line.floor_level_applied)
    : 'policy';
  return { value: line.floor_value_applied, source: `Set on ${level}.` };
}

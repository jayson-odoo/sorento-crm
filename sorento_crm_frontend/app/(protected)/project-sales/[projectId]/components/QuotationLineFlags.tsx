'use client';

import * as React from 'react';
import { TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useLineVerdict } from '../../_shared/hooks/useProjects';
import type {
  QuotationLine,
  QuotationLineVerdict,
} from '../../_shared/types/project.types';
import { formatMyr } from './QuotationsPanel';
import type { LineDraft } from './quotationLineDraft';

const FLOOR_LEVEL_LABELS: Record<string, string> = {
  product: 'this product',
  category: 'its category',
  category_ancestor: 'a parent category',
  system: 'the company default',
};

/**
 * What is true about the line, ON THE SPOT (the client: "cannot wait until I save").
 *
 * **Non-standard** is one word for two facts: no product and no set is linked (a fact about the
 * row on screen, read off the LIVE draft), or the linked product or set is outside the series
 * (the server's). A line never shows two pills. **Minimum price** is the server's too: while the
 * draft matches the saved row the saved verdicts show, and the moment it diverges the server is
 * asked (debounced, via `useLineVerdict`) with the same functions the save runs.
 *
 * Two cells read it (owner meeting, 29 Oct): Non-standard stays in the Product cell, the floor
 * sits under the price in the Rate cell and reads "Minimum price RM x". Both ask the same query
 * key, so React Query asks the server once.
 */
function useLineFacts(quotationId: string | null, line: QuotationLine | null, draft: LineDraft) {
  const productId = (draft.product_id ?? '').trim();
  const setId = (draft.product_set_id ?? '').trim();
  const price = (draft.unit_price ?? '').trim();
  const pristine =
    line != null &&
    (line.product_id ?? '') === productId &&
    (line.product_set_id ?? '') === setId &&
    (price || '') === (line.unit_price ?? '');
  const verdict = useLineVerdict(
    quotationId ?? '',
    {
      product_id: productId || undefined,
      product_set_id: setId || undefined,
      unit_price: price || undefined,
    },
    !pristine && quotationId !== null,
  );

  const belowFloor = pristine
    ? line.is_below_floor
    : Boolean(verdict.data?.is_below_floor);
  const nonStandard = pristine
    ? line.is_non_standard
    : Boolean(verdict.data?.is_non_standard);
  const floor = pristine
    ? describeFloor(line)
    : describeVerdictFloor(verdict.data ?? null);

  return { noTarget: !productId && !setId, belowFloor, nonStandard, floor };
}

/** The Product cell's flag: Non-standard, once. */
export function LineFlags({
  quotationId,
  line,
  draft,
}: {
  /** Null on a scope not saved yet: the verdict is asked of a saved scope only. */
  quotationId: string | null;
  line: QuotationLine | null;
  draft: LineDraft;
}) {
  const { noTarget, nonStandard } = useLineFacts(quotationId, line, draft);
  if (!noTarget && !nonStandard) return null;

  return (
    <div className="flex flex-wrap items-center gap-1">
      <Badge
        variant="secondary"
        className="gap-1 text-2xs"
        title={
          noTarget ? 'Not a catalogue product' : 'Outside the series this scope is quoted from'
        }
      >
        <TriangleAlert className="size-3" aria-hidden />
        Non-standard
      </Badge>
    </div>
  );
}

/** The Rate cell's flag, under the price: "Minimum price RM x" and where that was set. */
export function MinimumPriceFlag({
  quotationId,
  line,
  draft,
}: {
  quotationId: string | null;
  line: QuotationLine | null;
  draft: LineDraft;
}) {
  const { belowFloor, floor } = useLineFacts(quotationId, line, draft);
  if (!belowFloor) return null;

  return (
    <div className="mt-1 space-y-0.5 text-end">
      {/* No icon and tight padding: the Rate cell is narrow, and "Minimum" must fit on a line. */}
      <Badge
        variant="destructive"
        className="h-auto whitespace-normal rounded-md px-1.5 py-0.5 text-start text-2xs leading-tight"
        title={floor.source}
      >
        {floor.value ? `Minimum price ${formatMyr(floor.value)}` : 'Minimum price'}
      </Badge>
      <p className="whitespace-normal break-words text-2xs text-destructive">{floor.source}</p>
    </div>
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

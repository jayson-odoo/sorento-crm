'use client';

import * as React from 'react';
import type {
  SalesOrderDocumentSaveBody,
  SalesOrderLineWriteBody,
  StagedSalesOrderLine,
} from '../../../../_shared/types/projectSalesOrder.types';

/** The header fields of a sales order that a person may change, as strings. */
export type SalesOrderHeaderDraft = {
  area_group?: string;
};

/**
 * The edit view's state for one sales order draft.
 *
 * Nothing in here writes. It is the same session the quotation document already carries
 * (`useQuotationEditSession`): edits, additions and removals accumulate locally, and the
 * screen's ONE Save turns them into one whole-document write. The client's complaint against
 * the quotation was that "every addition of line doesn't trigger a save ... very annoying",
 * and a sales order is the same document with different columns.
 *
 * Simpler than the quotation's in one way, and it is worth saying why: a quotation document
 * holds several scopes, each with its own version and its own line set, so its session is
 * keyed by scope. A sales order holds ONE line set, so this holds one.
 */
export type SalesOrderEditSession = {
  isEditing: boolean;
  begin: () => void;
  /** Throw away everything staged and go back to the view. */
  cancel: () => void;
  /** The staged lines, or null until they have been seeded from the server's rows. */
  staged: StagedSalesOrderLine[] | null;
  /** First sight of the lines in edit mode: what the server has, as the starting point. */
  seed: (lines: StagedSalesOrderLine[]) => void;
  /** Every keystroke, addition and reorder in the line table. */
  stage: (lines: StagedSalesOrderLine[]) => void;
  /** Stage or unstage one line's removal. Reversible until Save, the commit point. */
  toggleRemoved: (key: string) => void;
  headerDraft: SalesOrderHeaderDraft;
  stageHeader: (patch: SalesOrderHeaderDraft) => void;
  /** Stored lines this Save would delete. Named in the one confirmation Save raises. */
  removedCount: number;
  /** Anything at all staged. Drives Save, and the warning on navigating away. */
  isDirty: boolean;
  /** Staged lines that are not ready to be written. Counted so a refusal can say how many. */
  unfinishedCount: number;
  /** The one request body: the header edits, plus the lines when they actually moved. */
  body: SalesOrderDocumentSaveBody;
};

function sameDraft(a: Record<string, string>, b: Record<string, string>): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    if ((a[key] ?? '') !== (b[key] ?? '')) return false;
  }
  return true;
}

function sameLines(a: StagedSalesOrderLine[], b: StagedSalesOrderLine[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((line, index) => {
    const other = b[index];
    return (
      line.key === other.key &&
      line.id === other.id &&
      line.removed === other.removed &&
      sameDraft(line.draft, other.draft)
    );
  });
}

/**
 * The one rule a sales order line has to satisfy before it can be stored.
 *
 * A quantity, and something to call the item. The product is optional because an unresolved
 * line is a real state on a drafted order (the `unresolved_product` finding exists for it),
 * but a line with neither a product nor a description is not a line anybody can read.
 */
export function salesOrderLineErrors(
  draft: Record<string, string>,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!draft.product_id && !(draft.description ?? '').trim()) {
    errors.description = 'Needed when no product is picked';
  }
  const qty = (draft.qty ?? '').trim();
  if (qty === '' || !/^\d*\.?\d+$/.test(qty) || Number(qty) <= 0) {
    errors.qty = 'A quantity above zero';
  }
  const price = (draft.unit_price ?? '').trim();
  if (price !== '' && (!/^\d*\.?\d+$/.test(price) || Number(price) < 0)) {
    errors.unit_price = 'Must be a number';
  }
  const delivery = (draft.delivery_date ?? '').trim();
  if (delivery !== '' && !/^\d{4}-\d{2}-\d{2}$/.test(delivery)) {
    errors.delivery_date = 'Use YYYY-MM-DD';
  }
  return errors;
}

/**
 * A staged set as the body of the whole-document write.
 *
 * Removed lines are simply left out, which is exactly how the endpoint deletes them, and a
 * line added in this session carries no `id` so the server reads it as new. Order is array
 * position; `line_no` is not sent at all.
 */
export function stagedLinesToBody(
  lines: StagedSalesOrderLine[],
): SalesOrderLineWriteBody[] {
  return lines
    .filter((line) => !line.removed)
    .map((line) => {
      const body: SalesOrderLineWriteBody = {
        product_id: line.draft.product_id || null,
        description: (line.draft.description ?? '').trim() || null,
        qty: (line.draft.qty ?? '').trim() || '0',
        uom: (line.draft.uom ?? '').trim() || null,
        unit_price: (line.draft.unit_price ?? '').trim() || '0',
        delivery_date: (line.draft.delivery_date ?? '').trim() || null,
        stock_location: (line.draft.stock_location ?? '').trim() || null,
      };
      return line.id ? { id: line.id, ...body } : body;
    });
}

export function useSalesOrderEditSession(): SalesOrderEditSession {
  const [isEditing, setIsEditing] = React.useState(false);
  const [seeded, setSeeded] = React.useState<StagedSalesOrderLine[] | null>(null);
  const [staged, setStaged] = React.useState<StagedSalesOrderLine[] | null>(null);
  const [headerDraft, setHeaderDraft] = React.useState<SalesOrderHeaderDraft>({});

  const begin = React.useCallback(() => setIsEditing(true), []);

  const cancel = React.useCallback(() => {
    // Everything at once, so there is no window in which the screen is half out of edit
    // mode. The table then re-reads the server's rows, which is what Cancel promises.
    setIsEditing(false);
    setSeeded(null);
    setStaged(null);
    setHeaderDraft({});
  }, []);

  const seed = React.useCallback((lines: StagedSalesOrderLine[]) => {
    // Seeded ONCE. A refetch landing mid-edit must not overwrite what somebody is typing,
    // and this is the only place the starting point is decided.
    setSeeded((previous) => previous ?? lines);
    setStaged((previous) => previous ?? lines);
  }, []);

  const stage = React.useCallback((lines: StagedSalesOrderLine[]) => {
    setStaged((previous) => {
      if (previous === null) return previous;
      // The table reports on every render, not only on every change. Returning the same
      // array for an identical set is what stops that turning into a render loop.
      if (sameLines(previous, lines)) return previous;
      return lines;
    });
  }, []);

  const toggleRemoved = React.useCallback((key: string) => {
    setStaged((previous) =>
      previous === null
        ? previous
        : previous.map((line) =>
            line.key === key ? { ...line, removed: !line.removed } : line,
          ),
    );
  }, []);

  const stageHeader = React.useCallback((patch: SalesOrderHeaderDraft) => {
    setHeaderDraft((previous) => ({ ...previous, ...patch }));
  }, []);

  const linesMoved =
    seeded !== null && staged !== null && !sameLines(seeded, staged);

  const removedCount = React.useMemo(
    () => (staged ?? []).filter((line) => line.removed && line.id !== null).length,
    [staged],
  );

  const unfinishedCount = React.useMemo(
    () =>
      (staged ?? []).filter(
        (line) =>
          !line.removed && Object.keys(salesOrderLineErrors(line.draft)).length > 0,
      ).length,
    [staged],
  );

  const isDirty = Object.keys(headerDraft).length > 0 || linesMoved;

  const body = React.useMemo<SalesOrderDocumentSaveBody>(() => {
    const next: SalesOrderDocumentSaveBody = {};
    // Only the keys somebody actually typed into: an absent key leaves the stored value
    // alone, so an untouched field cannot be blanked by a save.
    if (headerDraft.area_group !== undefined) {
      next.area_group = headerDraft.area_group.trim() || null;
    }
    // Lines are only sent when they moved. The write REPLACES the whole set, so sending an
    // untouched set back is a real rewrite of rows nobody edited, not a no-op.
    if (linesMoved && staged) next.lines = stagedLinesToBody(staged);
    return next;
  }, [headerDraft, linesMoved, staged]);

  return {
    isEditing,
    begin,
    cancel,
    staged,
    seed,
    stage,
    toggleRemoved,
    headerDraft,
    stageHeader,
    removedCount,
    isDirty,
    unfinishedCount,
    body,
  };
}

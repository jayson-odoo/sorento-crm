'use client';

import * as React from 'react';
import type { InlineDraft } from '../../../../_shared/components/InlineLineTable';
import type {
  ProjectPurchaseOrderBody,
  StagedPurchaseOrderLine,
} from '../../../../_shared/types/project.types';

/**
 * The edit view's state, for one customer PO.
 *
 * Nothing in here writes. It is the same answer the quotation document gives - edits, additions
 * and removals accumulate locally, and the screen's one Save turns them into one request - with
 * one simplification the PO earns honestly: a quotation document holds several scopes across
 * ROUTED tabs, so its session has to live in a shell and be keyed per scope. A PO is one header
 * and one line set on one page, so the session is flat and lives with the page.
 *
 * `seeded` is what the server had when the session opened. Dirty is measured against it rather
 * than against a "touched" flag, so typing a value and typing it back is not a change, and Save
 * stays disabled.
 */
export type PurchaseOrderEditSession = {
  isEditing: boolean;
  begin: () => void;
  /** Throw away everything staged and go back to the view. */
  cancel: () => void;
  /** The staged lines, or null until the line table has seeded them from the server. */
  staged: StagedPurchaseOrderLine[] | null;
  /** First sight of the lines in edit mode: what the server has, as the starting point. */
  seed: (lines: StagedPurchaseOrderLine[]) => void;
  /** Every keystroke and addition in the line table. */
  stage: (lines: StagedPurchaseOrderLine[]) => void;
  /** Stage or unstage one line's removal. Reversible until Save, which is the commit point. */
  toggleRemoved: (key: string) => void;
  /** The header fields, staged for the same one request the lines go in. */
  headerDraft: Partial<ProjectPurchaseOrderBody>;
  stageHeader: (patch: Partial<ProjectPurchaseOrderBody>) => void;
  /**
   * Whether the lines actually moved.
   *
   * The save REPLACES the whole set, so sending it back untouched is a real rewrite of rows
   * nobody edited, not a no-op. A session where only the header changed sends no `lines` key at
   * all.
   */
  linesChanged: boolean;
  /** Stored lines this Save would delete. Named in the one confirmation Save raises. */
  removedCount: number;
  /** Anything at all staged. Drives Save, and the warning on navigating away. */
  isDirty: boolean;
};

function sameDraft(a: InlineDraft, b: InlineDraft): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    if ((a[key] ?? '') !== (b[key] ?? '')) return false;
  }
  return true;
}

function sameLines(a: StagedPurchaseOrderLine[], b: StagedPurchaseOrderLine[]): boolean {
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

export function usePurchaseOrderEditSession(): PurchaseOrderEditSession {
  const [isEditing, setIsEditing] = React.useState(false);
  const [seeded, setSeeded] = React.useState<StagedPurchaseOrderLine[] | null>(null);
  const [staged, setStaged] = React.useState<StagedPurchaseOrderLine[] | null>(null);
  const [headerDraft, setHeaderDraft] = React.useState<Partial<ProjectPurchaseOrderBody>>({});

  const begin = React.useCallback(() => setIsEditing(true), []);

  const cancel = React.useCallback(() => {
    // Everything at once, so there is no window in which the screen is half out of edit mode.
    // The table then re-reads the server's rows, which is exactly what Cancel promises.
    setIsEditing(false);
    setSeeded(null);
    setStaged(null);
    setHeaderDraft({});
  }, []);

  const seed = React.useCallback((lines: StagedPurchaseOrderLine[]) => {
    // Seeded ONCE. A refetch landing mid-edit must not overwrite what somebody is typing, and
    // this is the only place the starting point is decided.
    setSeeded((previous) => previous ?? lines);
    setStaged((previous) => previous ?? lines);
  }, []);

  const stage = React.useCallback((lines: StagedPurchaseOrderLine[]) => {
    setStaged((previous) => {
      if (previous === null) return previous;
      // The table reports on every render, not only on every change. Returning the same object
      // for an identical set is what stops that turning into a render loop.
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

  const stageHeader = React.useCallback((patch: Partial<ProjectPurchaseOrderBody>) => {
    setHeaderDraft((previous) => ({ ...previous, ...patch }));
  }, []);

  const linesChanged = Boolean(seeded && staged && !sameLines(seeded, staged));
  const removedCount = (staged ?? []).filter((line) => line.removed && line.id !== null).length;
  const isDirty = Object.keys(headerDraft).length > 0 || linesChanged;

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
    linesChanged,
    removedCount,
    isDirty,
  };
}

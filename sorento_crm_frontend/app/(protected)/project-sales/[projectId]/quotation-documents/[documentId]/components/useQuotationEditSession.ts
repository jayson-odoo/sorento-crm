'use client';

import * as React from 'react';
import type { InlineDraft } from '../../../../_shared/components/InlineLineTable';
import type { StagedQuotationLine } from '../../../../_shared/types/project.types';
import type { QuotationDocumentBody } from '../../../../_shared/services/quotationDocumentService';

type StagedScope = {
  versionId: string;
  /** The lines as the server had them when this scope was opened. What Cancel and dirty compare. */
  seeded: StagedQuotationLine[];
  lines: StagedQuotationLine[];
};

/**
 * The edit view's state, for one quotation document.
 *
 * IT LIVES IN THE SHELL, and it has to: the document's tabs are ROUTES, so a panel unmounts the
 * moment the reader opens another tab. Anything held inside the scopes panel would be thrown away
 * by a trip to the terms and back, which is exactly the work somebody would be most annoyed to
 * lose. The shell outlives every tab, so the staged set lives there and reaches the panels through
 * `QuotationDocumentContext`.
 *
 * Nothing in here writes. It is the answer to the client's complaint that "every addition of line
 * doesn't trigger a save": edits, additions and removals accumulate here, and the screen's one
 * Save turns them into one bulk write per scope plus one document PATCH.
 */
export type QuotationEditSession = {
  isEditing: boolean;
  begin: () => void;
  /** Throw away everything staged and go back to the view. */
  cancel: () => void;
  /** Every scope opened in this session, by scope id. */
  scopes: Record<string, StagedScope>;
  /** First sight of a scope in edit mode: what the server has, as the starting point. */
  seedScope: (scopeId: string, versionId: string, lines: StagedQuotationLine[]) => void;
  /** Every keystroke, addition and reorder in one scope's table. */
  stageScope: (scopeId: string, lines: StagedQuotationLine[]) => void;
  /** Stage or unstage one line's removal. Reversible until Save, which is the commit point. */
  toggleRemoved: (scopeId: string, key: string) => void;
  /** The letterhead prose and header fields, staged for the one document PATCH. */
  documentDraft: QuotationDocumentBody;
  stageDocument: (patch: QuotationDocumentBody) => void;
  /**
   * Only the scopes whose lines actually moved.
   *
   * A scope the reader merely looked at is not re-written: the write replaces the WHOLE set, so
   * sending it back unchanged is a real rewrite of lines nobody touched, not a no-op.
   */
  changedScopes: { scopeId: string; versionId: string; lines: StagedQuotationLine[] }[];
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

function sameLines(a: StagedQuotationLine[], b: StagedQuotationLine[]): boolean {
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

export function useQuotationEditSession(): QuotationEditSession {
  const [isEditing, setIsEditing] = React.useState(false);
  const [scopes, setScopes] = React.useState<Record<string, StagedScope>>({});
  const [documentDraft, setDocumentDraft] = React.useState<QuotationDocumentBody>({});

  const begin = React.useCallback(() => setIsEditing(true), []);

  const cancel = React.useCallback(() => {
    // Everything at once, so there is no window in which the screen is half out of edit mode.
    // The panels then re-read the server's rows, which is exactly what Cancel promises.
    setIsEditing(false);
    setScopes({});
    setDocumentDraft({});
  }, []);

  const seedScope = React.useCallback(
    (scopeId: string, versionId: string, lines: StagedQuotationLine[]) => {
      setScopes((previous) => {
        // Seeded ONCE. A refetch landing mid-edit must not overwrite what somebody is typing,
        // and this is the only place a scope's starting point is decided.
        if (previous[scopeId]) return previous;
        return { ...previous, [scopeId]: { versionId, seeded: lines, lines } };
      });
    },
    [],
  );

  const stageScope = React.useCallback((scopeId: string, lines: StagedQuotationLine[]) => {
    setScopes((previous) => {
      const held = previous[scopeId];
      if (!held) return previous;
      // The table reports on every render, not only on every change. Returning the same object
      // for an identical set is what stops that turning into a render loop.
      if (sameLines(held.lines, lines)) return previous;
      return { ...previous, [scopeId]: { ...held, lines } };
    });
  }, []);

  const toggleRemoved = React.useCallback((scopeId: string, key: string) => {
    setScopes((previous) => {
      const held = previous[scopeId];
      if (!held) return previous;
      return {
        ...previous,
        [scopeId]: {
          ...held,
          lines: held.lines.map((line) =>
            line.key === key ? { ...line, removed: !line.removed } : line,
          ),
        },
      };
    });
  }, []);

  const stageDocument = React.useCallback((patch: QuotationDocumentBody) => {
    setDocumentDraft((previous) => ({ ...previous, ...patch }));
  }, []);

  const changedScopes = React.useMemo(
    () =>
      Object.entries(scopes)
        .filter(([, scope]) => !sameLines(scope.seeded, scope.lines))
        .map(([scopeId, scope]) => ({
          scopeId,
          versionId: scope.versionId,
          lines: scope.lines,
        })),
    [scopes],
  );

  const removedCount = React.useMemo(
    () =>
      Object.values(scopes).reduce(
        (total, scope) =>
          total + scope.lines.filter((line) => line.removed && line.id !== null).length,
        0,
      ),
    [scopes],
  );

  const isDirty = Object.keys(documentDraft).length > 0 || changedScopes.length > 0;

  return {
    isEditing,
    begin,
    cancel,
    scopes,
    seedScope,
    stageScope,
    toggleRemoved,
    documentDraft,
    stageDocument,
    changedScopes,
    removedCount,
    isDirty,
  };
}

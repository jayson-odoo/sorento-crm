'use client';

import * as React from 'react';
import type { ExpandedState } from '@tanstack/react-table';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

/**
 * One open decision row at a time, and never over an unsaved edit (C3/C5).
 *
 * Both readings of the board decide in the row - the cell's breakdown table and the List
 * view - and the two must teach one gesture: the whole row toggles, opening another closes
 * the first, and a half-composed amendment is not swallowed without being asked about. Held
 * here rather than written twice, so the question a planner is asked cannot come to differ
 * between two screens showing the same lines.
 */
export interface DecisionRowExpansion {
  expanded: ExpandedState;
  setExpanded: React.Dispatch<React.SetStateAction<ExpandedState>>;
  /** The row currently open, or null. */
  openKey: string | null;
  /** Reported by the panel: whether the open row holds an edit nobody has saved. */
  setDirty: (dirty: boolean) => void;
  /** Toggle a row, asking first when the open one holds unsaved work. */
  requestRow: (key: string) => void;
  /**
   * Close the CONTAINER the open row lives in - the cell dialog's X, its Escape key and its
   * backdrop - asking first when that row holds unsaved work.
   *
   * The prompt guarded one gesture and not the three easiest ones on the screen: the dialog
   * closed on any of them and the half-composed decision went with it, without a word.
   */
  requestClose: (close: () => void) => void;
  /** The row the planner asked for while the open one still held that work. */
  pending: string | null;
  /** Whether the unsaved-work question is on screen, for either reason. */
  prompting: boolean;
  keepEditing: () => void;
  discard: () => void;
}

export function useDecisionRowExpansion(): DecisionRowExpansion {
  const [expanded, setExpanded] = React.useState<ExpandedState>({});
  const [dirty, setDirty] = React.useState(false);
  const [pending, setPending] = React.useState<string | null>(null);
  /** The container's own close, held back until the question has been answered. */
  const [pendingClose, setPendingClose] = React.useState<(() => void) | null>(null);

  const openKey = React.useMemo(() => {
    if (typeof expanded === 'boolean') return null;
    return Object.keys(expanded).find((key) => expanded[key]) ?? null;
  }, [expanded]);

  const openRow = React.useCallback((key: string | null) => {
    setDirty(false);
    setExpanded(key ? { [key]: true } : {});
  }, []);

  const requestRow = React.useCallback(
    (key: string) => {
      const next = openKey === key ? null : key;
      if (dirty) {
        // `''` means "close the open row"; a key means "open that one instead".
        setPending(next ?? '');
        return;
      }
      openRow(next);
    },
    [dirty, openKey, openRow],
  );

  const requestClose = React.useCallback(
    (close: () => void) => {
      if (!dirty) {
        close();
        return;
      }
      // The state holds the callback itself, so the updater has to RETURN it rather than be
      // mistaken for one.
      setPendingClose(() => close);
    },
    [dirty],
  );

  const keepEditing = React.useCallback(() => {
    setPending(null);
    setPendingClose(null);
  }, []);
  const discard = React.useCallback(() => {
    if (pendingClose) {
      openRow(null);
      setPendingClose(null);
      pendingClose();
      return;
    }
    openRow(pending ? pending : null);
    setPending(null);
  }, [openRow, pending, pendingClose]);

  return {
    expanded,
    setExpanded,
    openKey,
    setDirty,
    requestRow,
    requestClose,
    pending,
    prompting: pending !== null || pendingClose !== null,
    keepEditing,
    discard,
  };
}

/**
 * Confirm before an edit is thrown away, the same rule every destructive action on this
 * product follows. `AlertDialog`, never `confirm()`.
 */
export function UnsavedDecisionPrompt({ state }: { state: DecisionRowExpansion }) {
  return (
    <AlertDialog
      open={state.prompting}
      onOpenChange={(next) => !next && state.keepEditing()}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Leave this decision unsaved?</AlertDialogTitle>
          <AlertDialogDescription>
            The composition you typed on this line has not been saved. Closing it discards it.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep editing</AlertDialogCancel>
          <AlertDialogAction onClick={state.discard}>Discard</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

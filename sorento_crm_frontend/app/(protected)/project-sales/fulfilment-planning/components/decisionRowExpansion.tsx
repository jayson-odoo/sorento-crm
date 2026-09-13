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
 * Decision rows that open in place, and never over an unsaved edit (C3/C5).
 *
 * Both readings of the board decide in the row - the cell's breakdown table and the List
 * view - and the two must teach one gesture: the whole row toggles, and a half-composed
 * amendment is not swallowed without being asked about. Held here rather than written twice,
 * so the question a planner is asked cannot come to differ between two screens showing the
 * same lines.
 *
 * HOW MANY AT ONCE differs, and only there. The cell dialog opens ONE row: it is a narrow
 * surface about a single product and date, so opening another closes the one before it - and
 * asks first, because that close is what throws the edit away. The list opens as many as the
 * planner wants (AC-C12, owner feedback 13 September 2026, "just like reorder planning"), so
 * opening a second row there discards NOTHING and asks nothing; only closing a dirty row, or
 * a Collapse all over one, is a question - and Collapse all asks it once for the lot.
 */
export interface DecisionRowExpansion {
  expanded: ExpandedState;
  setExpanded: React.Dispatch<React.SetStateAction<ExpandedState>>;
  /** The first row currently open, or null. */
  openKey: string | null;
  /** Every row currently open. */
  openKeys: string[];
  /** Reported by the panel: whether the row it is in holds an edit nobody has saved. */
  setDirty: (dirty: boolean) => void;
  /** The same, named (the list runs several panels at once, so a bare boolean is ambiguous). */
  setDirtyFor: (key: string, dirty: boolean) => void;
  /**
   * The named setter as ONE STABLE function per row.
   *
   * `BoardLineDecisionPanel` keeps `onDirtyChange` in the dependencies of an unmount effect
   * that reports the row clean, so an inline `(dirty) => setDirtyFor(key, dirty)` is a new
   * function on every render, the effect tears down and re-runs on every render, and the
   * report loops until React gives up ("Maximum update depth exceeded"). Cached per key, it
   * runs exactly when the row does.
   */
  dirtySetterFor: (key: string) => (dirty: boolean) => void;
  /** Toggle a row, asking first when what it would close holds unsaved work. */
  requestRow: (key: string) => void;
  /** Open every row named, in one go. Opening throws nothing away, so nothing is asked. */
  expandAll: (keys: string[]) => void;
  /** Close every open row, asking ONCE when any of them holds unsaved work. */
  requestCollapseAll: () => void;
  /**
   * Close the CONTAINER the open row lives in - the cell dialog's X, its Escape key and its
   * backdrop - asking first when that row holds unsaved work.
   *
   * The prompt guarded one gesture and not the three easiest ones on the screen: the dialog
   * closed on any of them and the half-composed decision went with it, without a word.
   */
  requestClose: (close: () => void) => void;
  /** Whether the unsaved-work question is on screen, for any of the reasons above. */
  prompting: boolean;
  keepEditing: () => void;
  discard: () => void;
}

/** What the planner asked for while an open row still held unsaved work. */
type PendingAction =
  | { kind: 'toggle'; key: string }
  | { kind: 'collapseAll' }
  | { kind: 'close'; close: () => void };

export function useDecisionRowExpansion(
  options: { multiple?: boolean } = {},
): DecisionRowExpansion {
  const multiple = options.multiple ?? false;
  const [expanded, setExpanded] = React.useState<ExpandedState>({});
  /** Which OPEN rows hold an edit nobody has saved. Per row: the list runs several. */
  const [dirtyKeys, setDirtyKeys] = React.useState<string[]>([]);
  const [pending, setPending] = React.useState<PendingAction | null>(null);

  const openKeys = React.useMemo(() => {
    if (typeof expanded === 'boolean') return [];
    return Object.keys(expanded).filter((key) => expanded[key]);
  }, [expanded]);
  const openKey = openKeys[0] ?? null;

  const setDirtyFor = React.useCallback((key: string, dirty: boolean) => {
    setDirtyKeys((current) => {
      const held = current.includes(key);
      if (dirty === held) return current;
      return dirty ? [...current, key] : current.filter((entry) => entry !== key);
    });
  }, []);

  /**
   * The single-row form the cell dialog keeps: it opens one panel, so "dirty" can only ever
   * be about that one, and naming it here would make every caller repeat the key it already
   * opened.
   */
  const setDirty = React.useCallback(
    (dirty: boolean) => {
      setDirtyKeys((current) => {
        if (!dirty) return current.length === 0 ? current : [];
        const key = openKeys[0] ?? '';
        return current.includes(key) ? current : [...current, key];
      });
    },
    [openKeys],
  );

  const setters = React.useRef(new Map<string, (dirty: boolean) => void>());
  const dirtySetterFor = React.useCallback(
    (key: string) => {
      const held = setters.current.get(key);
      if (held) return held;
      const setter = (dirty: boolean) => setDirtyFor(key, dirty);
      setters.current.set(key, setter);
      return setter;
    },
    [setDirtyFor],
  );

  const toggle = React.useCallback(
    (key: string) => {
      const record = typeof expanded === 'boolean' ? {} : expanded;
      if (record[key]) {
        // Closing the one that was clicked, and only it: after Expand all the rest are
        // somebody's deliberate state, not leftovers. Only ITS unsaved flag is cleared -
        // wiping the lot here left a dirty row still open with nothing marking it, and the
        // next Collapse all threw that edit away without asking.
        setDirtyFor(key, false);
        const next = { ...record };
        delete next[key];
        setExpanded(next);
        return;
      }
      if (multiple) {
        // Opening a second row closes nothing, so there is nothing to forget.
        setExpanded({ ...record, [key]: true });
        return;
      }
      // One at a time: opening this one CLOSES whatever was open, so whatever that row held
      // is gone with it, and the flag goes too.
      setDirtyKeys([]);
      setExpanded({ [key]: true });
    },
    [expanded, multiple, setDirtyFor],
  );

  const collapseAll = React.useCallback(() => {
    setDirtyKeys([]);
    setExpanded({});
  }, []);

  const requestRow = React.useCallback(
    (key: string) => {
      const record = typeof expanded === 'boolean' ? {} : expanded;
      const isOpen = Boolean(record[key]);
      // What a toggle would THROW AWAY is the question: closing a dirty row, or - on the
      // single-open reading - opening another over one. Opening a second row where several
      // may stand loses nothing, so nothing is asked.
      const losing = isOpen
        ? dirtyKeys.includes(key)
        : !multiple && dirtyKeys.length > 0;
      if (losing) {
        setPending({ kind: 'toggle', key });
        return;
      }
      toggle(key);
    },
    [dirtyKeys, expanded, multiple, toggle],
  );

  const expandAll = React.useCallback((keys: string[]) => {
    setExpanded(Object.fromEntries(keys.map((key) => [key, true])));
  }, []);

  const requestCollapseAll = React.useCallback(() => {
    // ONE question for the whole gesture, not one per open row: the planner pressed a single
    // control, and being asked six times would teach them to stop reading it.
    if (dirtyKeys.length > 0) {
      setPending({ kind: 'collapseAll' });
      return;
    }
    collapseAll();
  }, [collapseAll, dirtyKeys]);

  const requestClose = React.useCallback(
    (close: () => void) => {
      if (dirtyKeys.length === 0) {
        close();
        return;
      }
      setPending({ kind: 'close', close });
    },
    [dirtyKeys],
  );

  const keepEditing = React.useCallback(() => setPending(null), []);

  const discard = React.useCallback(() => {
    if (!pending) return;
    setPending(null);
    if (pending.kind === 'toggle') {
      toggle(pending.key);
      return;
    }
    if (pending.kind === 'collapseAll') {
      collapseAll();
      return;
    }
    collapseAll();
    pending.close();
  }, [collapseAll, pending, toggle]);

  return {
    expanded,
    setExpanded,
    openKey,
    openKeys,
    setDirty,
    setDirtyFor,
    dirtySetterFor,
    requestRow,
    expandAll,
    requestCollapseAll,
    requestClose,
    prompting: pending !== null,
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

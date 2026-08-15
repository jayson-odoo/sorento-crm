/**
 * Undo and redo, as whole states rather than patches.
 *
 * An entry is a complete picture of the room. That costs a little memory and
 * buys the one property that matters: restoring an entry can never dangle a
 * reference to something that has since been deleted. IKEA's planner stores
 * something cleverer and undoing a newly added door crashes it outright,
 * leaving the saved session unopenable - a bug the user cannot even work around
 * by reloading.
 */

export interface History<T> {
  past: T[];
  present: T;
  future: T[];
}

/**
 * How many steps back you can go.
 *
 * Deep enough to cover a session's worth of nudging, shallow enough that a room
 * full of products never turns the stack into a memory problem.
 */
export const HISTORY_LIMIT = 50;

function clone<T>(value: T): T {
  return structuredClone(value);
}

export function newHistory<T>(present: T): History<T> {
  return { past: [], present: clone(present), future: [] };
}

/**
 * Record a new state.
 *
 * Identical states are dropped: a drag emits a state per frame, and without
 * this one Ctrl-Z would appear to do nothing while it stepped through fifty
 * indistinguishable entries.
 */
export function pushHistory<T>(history: History<T>, present: T): History<T> {
  if (JSON.stringify(history.present) === JSON.stringify(present)) return history;

  const past = [...history.past, history.present];
  return {
    past: past.length > HISTORY_LIMIT ? past.slice(past.length - HISTORY_LIMIT) : past,
    present: clone(present),
    // Editing after an undo abandons the old redo trail, which no longer
    // follows from where you are.
    future: [],
  };
}

export function canUndo<T>(history: History<T>): boolean {
  return history.past.length > 0;
}

export function canRedo<T>(history: History<T>): boolean {
  return history.future.length > 0;
}

export function undo<T>(history: History<T>): History<T> {
  if (!canUndo(history)) return history;
  const previous = history.past[history.past.length - 1];
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future],
  };
}

export function redo<T>(history: History<T>): History<T> {
  if (!canRedo(history)) return history;
  const [next, ...rest] = history.future;
  return {
    past: [...history.past, history.present],
    present: next,
    future: rest,
  };
}

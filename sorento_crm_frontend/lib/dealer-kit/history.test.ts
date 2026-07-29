/**
 * Undo/redo for the room, written before the implementation.
 *
 * IKEA's planner is the cautionary tale here: undoing a freshly added door
 * crashed their app to a raw stack trace and left the autosaved session
 * unopenable. The lesson taken is that an entry must be a COMPLETE, standalone
 * picture of the room - never a patch that assumes what it is being applied to.
 * Restoring one can then never dangle a reference to something that no longer
 * exists.
 */
import { describe, expect, it } from 'vitest';

import { HISTORY_LIMIT, canRedo, canUndo, pushHistory, redo, undo, type History } from './history';

interface Room {
  width: number;
}

const start: History<Room> = { past: [], present: { width: 4000 }, future: [] };

describe('pushHistory', () => {
  it('moves the old state into the past', () => {
    const next = pushHistory(start, { width: 4500 });

    expect(next.present).toEqual({ width: 4500 });
    expect(next.past).toEqual([{ width: 4000 }]);
  });

  it('drops the redo trail once you edit again', () => {
    // Otherwise "undo, change your mind, redo" replays a future that never
    // followed from the state you are now in.
    const edited = pushHistory(start, { width: 4500 });
    const undone = undo(edited);
    const diverged = pushHistory(undone, { width: 3000 });

    expect(diverged.future).toEqual([]);
    expect(canRedo(diverged)).toBe(false);
  });

  it('ignores a push that changes nothing', () => {
    // Pointer noise during a drag would otherwise fill the stack with dozens of
    // identical entries and make one Ctrl-Z do nothing visible.
    const next = pushHistory(start, { width: 4000 });

    expect(next).toBe(start);
  });

  it('forgets the oldest entries rather than growing without limit', () => {
    let history = start;
    for (let step = 1; step <= HISTORY_LIMIT + 10; step += 1) {
      history = pushHistory(history, { width: 4000 + step });
    }

    expect(history.past).toHaveLength(HISTORY_LIMIT);
    // The very first room is gone; the most recent ones are all there.
    expect(history.past[0]).not.toEqual({ width: 4000 });
    expect(history.past.at(-1)).toEqual({ width: 4000 + HISTORY_LIMIT + 9 });
  });

  it('stores a copy, so mutating the object afterwards cannot rewrite history', () => {
    const room = { width: 4500 };
    const next = pushHistory(start, room);
    room.width = 9999;

    expect(next.present).toEqual({ width: 4500 });
  });
});

describe('undo and redo', () => {
  it('walks back and forward through the states', () => {
    const one = pushHistory(start, { width: 4500 });
    const two = pushHistory(one, { width: 5000 });

    const back = undo(two);
    expect(back.present).toEqual({ width: 4500 });

    const backAgain = undo(back);
    expect(backAgain.present).toEqual({ width: 4000 });

    const forward = redo(backAgain);
    expect(forward.present).toEqual({ width: 4500 });
  });

  it('does nothing at either end instead of throwing', () => {
    expect(undo(start)).toBe(start);
    expect(redo(start)).toBe(start);
    expect(canUndo(start)).toBe(false);
    expect(canRedo(start)).toBe(false);
  });

  it('knows what it can do', () => {
    const one = pushHistory(start, { width: 4500 });

    expect(canUndo(one)).toBe(true);
    expect(canRedo(one)).toBe(false);
    expect(canRedo(undo(one))).toBe(true);
  });
});

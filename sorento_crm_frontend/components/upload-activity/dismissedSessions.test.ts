import { describe, it, expect, beforeEach } from 'vitest';

import {
  clearDismissed,
  dismissSessions,
  getDismissedSnapshot,
  pruneDismissed,
  subscribeDismissed,
} from './dismissedSessions';

describe('dismissedSessions', () => {
  beforeEach(() => {
    window.localStorage.clear();
    clearDismissed();
  });

  it('remembers dismissed ids across a reload', () => {
    dismissSessions(['a', 'b']);
    expect([...getDismissedSnapshot()]).toEqual(['a', 'b']);
    // What a fresh page load would read back.
    expect(
      JSON.parse(
        window.localStorage.getItem('sorento:upload-activity:dismissed') ?? '[]',
      ),
    ).toEqual(['a', 'b']);
  });

  it('keeps snapshot identity stable when nothing changes', () => {
    dismissSessions(['a']);
    const first = getDismissedSnapshot();
    dismissSessions(['a']); // already known — must not produce a new snapshot
    expect(getDismissedSnapshot()).toBe(first);
  });

  it('notifies subscribers on change only', () => {
    let calls = 0;
    const unsubscribe = subscribeDismissed(() => {
      calls += 1;
    });
    dismissSessions(['a']);
    expect(calls).toBe(1);
    dismissSessions(['a']);
    expect(calls).toBe(1);
    unsubscribe();
    dismissSessions(['b']);
    expect(calls).toBe(1);
  });

  it('prunes ids the feed no longer returns', () => {
    dismissSessions(['a', 'b', 'c']);
    pruneDismissed(['b']);
    expect([...getDismissedSnapshot()]).toEqual(['b']);
  });

  it('survives localStorage throwing', () => {
    const original = window.localStorage.getItem;
    // Private-mode style failure on read.
    window.localStorage.getItem = () => {
      throw new Error('denied');
    };
    clearDismissed();
    expect(() => getDismissedSnapshot()).not.toThrow();
    window.localStorage.getItem = original;
  });
});

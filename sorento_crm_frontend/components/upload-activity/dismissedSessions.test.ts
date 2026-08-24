import { describe, it, expect, beforeEach } from 'vitest';

import {
  clearDismissed,
  dismissKey,
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

  it('prunes entries whose session the feed no longer returns', () => {
    dismissSessions(['a', 'b', 'c']);
    pruneDismissed(['b']);
    expect([...getDismissedSnapshot()]).toEqual(['b']);
  });

  it('prunes on the session id, so a state change does not delete the record', () => {
    const stuck = { session_id: 'sess-1', status: 'processing', needs_action: false };
    dismissSessions([dismissKey(stuck)]);
    pruneDismissed(['sess-1']); // still in the feed, now failed
    expect([...getDismissedSnapshot()]).toEqual(['sess-1:processing:0']);
  });

  it('keys on the state, so the same session in a new state is not dismissed', () => {
    const stuck = { session_id: 'sess-1', status: 'processing', needs_action: false };
    dismissSessions([dismissKey(stuck)]);
    const seen = new Set(getDismissedSnapshot());
    expect(seen.has(dismissKey(stuck))).toBe(true);
    // The stuck upload finally answers, with an error.
    const failed = { session_id: 'sess-1', status: 'failed', needs_action: true };
    expect(seen.has(dismissKey(failed))).toBe(false);
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

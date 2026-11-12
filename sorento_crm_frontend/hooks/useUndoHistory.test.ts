/**
 * The shared undo / redo history (PROJECT-QUOTE-LINE-TOOLS, owner hand test 11 Nov: "just need to
 * have an undo / redo function, see can reuse our price tag template designer"). It is the price
 * tag designer's history, made generic: the designer and the quotation lines editor both use it.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useUndoHistory } from './useUndoHistory';

type Row = { id: string; price: string };

function setup(initial: Row[] = [{ id: 'a', price: '1' }]) {
  return renderHook(() => useUndoHistory<Row[]>(initial));
}

describe('useUndoHistory', () => {
  it('undoes and redoes whole snapshots, newest first', () => {
    const { result } = setup();
    act(() => result.current.pushState([{ id: 'a', price: '2' }]));
    act(() => result.current.pushState([{ id: 'a', price: '3' }]));
    expect(result.current.canUndo).toBe(true);

    let restored: Row[] | null = null;
    act(() => {
      restored = result.current.undo();
    });
    expect(restored).toEqual([{ id: 'a', price: '2' }]);
    act(() => {
      restored = result.current.undo();
    });
    expect(restored).toEqual([{ id: 'a', price: '1' }]);
    expect(result.current.canUndo).toBe(false);
    act(() => {
      restored = result.current.redo();
    });
    expect(restored).toEqual([{ id: 'a', price: '2' }]);
    expect(result.current.canRedo).toBe(true);
  });

  it('a value equal to the current one is no step', () => {
    const { result } = setup();
    act(() => result.current.pushState([{ id: 'a', price: '1' }]));
    expect(result.current.canUndo).toBe(false);
  });

  it('a new step clears redo', () => {
    const { result } = setup();
    act(() => result.current.pushState([{ id: 'a', price: '2' }]));
    act(() => {
      result.current.undo();
    });
    act(() => result.current.pushState([{ id: 'a', price: '9' }]));
    expect(result.current.canRedo).toBe(false);
  });

  it('merge replaces the current step instead of adding one (typing one field)', () => {
    const { result } = setup();
    act(() => result.current.pushState([{ id: 'a', price: '8' }]));
    act(() => result.current.pushState([{ id: 'a', price: '85' }], { merge: true }));
    act(() => result.current.pushState([{ id: 'a', price: '850' }], { merge: true }));
    let restored: Row[] | null = null;
    act(() => {
      restored = result.current.undo();
    });
    expect(restored).toEqual([{ id: 'a', price: '1' }]);
    expect(result.current.canUndo).toBe(false);
  });

  it('reset starts a fresh history from the given state', () => {
    const { result } = setup();
    act(() => result.current.pushState([{ id: 'a', price: '2' }]));
    act(() => result.current.reset([{ id: 'b', price: '5' }]));
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);
    act(() => result.current.pushState([{ id: 'b', price: '6' }]));
    let restored: Row[] | null = null;
    act(() => {
      restored = result.current.undo();
    });
    expect(restored).toEqual([{ id: 'b', price: '5' }]);
  });

  it('keeps at most 50 steps', () => {
    const { result } = setup();
    for (let n = 2; n <= 60; n += 1) {
      act(() => result.current.pushState([{ id: 'a', price: String(n) }]));
    }
    let undos = 0;
    act(() => {
      while (result.current.undo()) undos += 1;
    });
    expect(undos).toBe(50);
  });

  it('hands back copies: mutating a restored snapshot never edits the history', () => {
    const { result } = setup();
    act(() => result.current.pushState([{ id: 'a', price: '2' }]));
    let restored: Row[] | null = null;
    act(() => {
      restored = result.current.undo();
    });
    (restored as unknown as Row[])[0].price = 'x';
    act(() => {
      result.current.redo();
    });
    act(() => {
      restored = result.current.undo();
    });
    expect(restored).toEqual([{ id: 'a', price: '1' }]);
  });
});

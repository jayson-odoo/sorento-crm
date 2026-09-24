/**
 * useCellSelection - Excel-style rectangle selection (R7, AC-25 to AC-32).
 *
 * Phase 1 already built this hook in full (it has no backend dependency and needed
 * nothing from Phase 2), so most of the assertions below are expected to pass today -
 * this file exists to give it the test coverage Phase 1 explicitly deferred
 * (PRINCIPLES.md: "Phase 1 ... no tests yet"), traced one-for-one to the UAC it was
 * built against, rather than to prove a red-before-green cutover the way the backend
 * and `stockDebtService.real.test.ts` do. Any assertion that DOES fail here is a real
 * defect in the shipped Phase-1 hook, not a missing Phase-2 feature.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useCellSelection } from './useCellSelection';

const ROW_IDS = ['r1', 'r2', 'r3'];
const COLUMN_KEYS = ['2026-09', '2026-10', '2026-11'];

const VALUES: Record<string, number | null> = {
  'r1::2026-09': 10,
  'r1::2026-10': 20,
  'r1::2026-11': -5,
  'r2::2026-09': -30,
  'r2::2026-10': null,
  'r2::2026-11': 8,
  'r3::2026-09': 0,
  'r3::2026-10': 15,
  'r3::2026-11': -2,
};

function getValue(rowId: string, columnKey: string): number | null {
  return VALUES[`${rowId}::${columnKey}`] ?? null;
}

function pointerEvent(overrides: Partial<{
  button: number;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  buttons: number;
  clientX: number;
  clientY: number;
}> = {}) {
  return {
    button: 0,
    shiftKey: false,
    ctrlKey: false,
    metaKey: false,
    buttons: 1,
    clientX: 0,
    clientY: 0,
    ...overrides,
  } as unknown as React.PointerEvent;
}

function mouseEvent(overrides: Partial<{ shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }> = {}) {
  return { shiftKey: false, ctrlKey: false, metaKey: false, ...overrides } as unknown as React.MouseEvent;
}

function keyEvent(key: string, overrides: Partial<{ shiftKey: boolean }> = {}) {
  return {
    key,
    shiftKey: true,
    preventDefault() {},
    ...overrides,
  } as unknown as React.KeyboardEvent;
}

function setup() {
  return renderHook(() =>
    useCellSelection({ rowIds: ROW_IDS, columnKeys: COLUMN_KEYS, getValue }),
  );
}

describe('useCellSelection - drag rectangle (AC-25)', () => {
  it('selects the rectangle a drag spans, past the 4px threshold', () => {
    const { result } = setup();
    act(() => {
      result.current.onCellPointerDown('r1', '2026-09', pointerEvent());
    });
    act(() => {
      result.current.onCellPointerEnter(
        'r2',
        '2026-10',
        pointerEvent({ clientX: 20, clientY: 20 }),
      );
    });
    expect(result.current.isSelected('r1', '2026-09')).toBe(true);
    expect(result.current.isSelected('r1', '2026-10')).toBe(true);
    expect(result.current.isSelected('r2', '2026-09')).toBe(true);
    expect(result.current.isSelected('r2', '2026-10')).toBe(true);
    expect(result.current.isSelected('r3', '2026-11')).toBe(false);
    expect(result.current.selectedCount).toBe(4);
  });

  it('a plain click with no drag opens the drill and leaves nothing selected', () => {
    const { result } = setup();
    act(() => {
      result.current.onCellPointerDown('r1', '2026-09', pointerEvent());
    });
    let opensDrill = false;
    act(() => {
      opensDrill = result.current.onCellClick('r1', '2026-09', mouseEvent());
    });
    expect(opensDrill).toBe(true);
    expect(result.current.selectedCount).toBe(0);
  });

  it('the click that ends a drag does not also open the drill (AC-31)', () => {
    const { result } = setup();
    act(() => {
      result.current.onCellPointerDown('r1', '2026-09', pointerEvent());
    });
    act(() => {
      result.current.onCellPointerEnter(
        'r2',
        '2026-10',
        pointerEvent({ clientX: 20, clientY: 20 }),
      );
    });
    let opensDrill = true;
    act(() => {
      opensDrill = result.current.onCellClick('r2', '2026-10', mouseEvent());
    });
    expect(opensDrill).toBe(false);
    // The rectangle the drag drew is still selected - the release click did not clear it.
    expect(result.current.isSelected('r1', '2026-09')).toBe(true);
  });
});

describe('useCellSelection - shift/cmd click (AC-26)', () => {
  it('shift+click extends the rectangle from the anchor', () => {
    const { result } = setup();
    act(() => {
      result.current.onCellClick('r1', '2026-09', mouseEvent());
    });
    act(() => {
      result.current.onCellClick('r3', '2026-11', mouseEvent({ shiftKey: true }));
    });
    expect(result.current.selectedCount).toBe(9);
    expect(result.current.isSelected('r2', '2026-10')).toBe(true);
  });

  it('cmd/ctrl+click toggles exactly the pressed cell', () => {
    const { result } = setup();
    act(() => {
      result.current.onCellClick('r1', '2026-09', mouseEvent({ metaKey: true }));
    });
    expect(result.current.isSelected('r1', '2026-09')).toBe(true);
    act(() => {
      result.current.onCellClick('r2', '2026-10', mouseEvent({ ctrlKey: true }));
    });
    expect(result.current.isSelected('r1', '2026-09')).toBe(true);
    expect(result.current.isSelected('r2', '2026-10')).toBe(true);
    expect(result.current.selectedCount).toBe(2);
    act(() => {
      result.current.onCellClick('r1', '2026-09', mouseEvent({ metaKey: true }));
    });
    expect(result.current.isSelected('r1', '2026-09')).toBe(false);
    expect(result.current.selectedCount).toBe(1);
  });
});

describe('useCellSelection - column header (AC-27)', () => {
  it('selects the whole column on the page', () => {
    const { result } = setup();
    act(() => {
      result.current.onColumnHeaderClick('2026-11');
    });
    expect(result.current.selectedCount).toBe(3);
    ROW_IDS.forEach((rowId) => expect(result.current.isSelected(rowId, '2026-11')).toBe(true));
  });
});

describe('useCellSelection - summary bar (AC-28)', () => {
  it('is null below two selected values', () => {
    const { result } = setup();
    act(() => {
      result.current.onCellClick('r1', '2026-09', mouseEvent({ metaKey: true }));
    });
    expect(result.current.summary).toBeNull();
  });

  it('states count / sum / avg / min / max once 2+ are selected, ignoring nulls', () => {
    const { result } = setup();
    act(() => {
      result.current.onColumnHeaderClick('2026-09');
    });
    // r1=10, r2=-30, r3=0
    expect(result.current.summary).toEqual({ count: 3, sum: -20, avg: -20 / 3, min: -30, max: 10 });
  });

  it('excludes a null-valued cell from the summary even though it is selected', () => {
    const { result } = setup();
    act(() => {
      result.current.onColumnHeaderClick('2026-10');
    });
    // r1=20, r2=null (unselectable value), r3=15 -> count is 2, not 3
    expect(result.current.summary).toEqual({ count: 2, sum: 35, avg: 17.5, min: 15, max: 20 });
  });
});

describe('useCellSelection - escape and clear (AC-29)', () => {
  it('clear() empties the selection', () => {
    const { result } = setup();
    act(() => {
      result.current.onColumnHeaderClick('2026-09');
    });
    expect(result.current.selectedCount).toBe(3);
    act(() => {
      result.current.clear();
    });
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.summary).toBeNull();
  });

  it('an Escape keydown on the window clears the selection', () => {
    const { result } = setup();
    act(() => {
      result.current.onColumnHeaderClick('2026-09');
    });
    expect(result.current.selectedCount).toBe(3);
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(result.current.selectedCount).toBe(0);
  });
});

describe('useCellSelection - copy (AC-30)', () => {
  it('prints the selected rectangle as tab-separated rows in grid order', () => {
    const { result } = setup();
    act(() => {
      result.current.onCellClick('r1', '2026-09', mouseEvent());
    });
    act(() => {
      result.current.onCellClick('r2', '2026-10', mouseEvent({ shiftKey: true }));
    });
    expect(result.current.copyText()).toBe('10\t20\n-30\t');
  });
});

describe('useCellSelection - keyboard (AC-32)', () => {
  it('Shift+ArrowRight grows the rectangle from the focused cell', () => {
    const { result } = setup();
    act(() => {
      result.current.onCellClick('r1', '2026-09', mouseEvent());
    });
    let next: { rowId: string; columnKey: string } | null = null;
    act(() => {
      next = result.current.onCellKeyDown('r1', '2026-09', keyEvent('ArrowRight'));
    });
    expect(next).toEqual({ rowId: 'r1', columnKey: '2026-10' });
    expect(result.current.isSelected('r1', '2026-09')).toBe(true);
    expect(result.current.isSelected('r1', '2026-10')).toBe(true);
    expect(result.current.selectedCount).toBe(2);
  });

  it('a key without Shift is not handled', () => {
    const { result } = setup();
    let next: { rowId: string; columnKey: string } | null = { rowId: 'x', columnKey: 'y' };
    act(() => {
      next = result.current.onCellKeyDown('r1', '2026-09', keyEvent('ArrowRight', { shiftKey: false }));
    });
    expect(next).toBeNull();
  });
});

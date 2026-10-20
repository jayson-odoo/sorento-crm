/**
 * OI-SPLIT-GUIDE F13: the edit sheet opened from the Confirm guide is scoped to the lines this
 * Confirm covers (`onlyLineIds`) plus the lines their saved splits sit on; no "Split lines only"
 * toggle and no search there. Unscoped (the board's gear) it is unchanged: every line, with the
 * toggle (regression pin).
 */
import { cleanup, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { blockIds, renderDialog, savedCase, sheet, wireSplit } from '@/test-mocks/lineSplitSheetKit';

const { getLineSplits, saveLineSplits } = vi.hoisted(() => ({
  getLineSplits: vi.fn(),
  saveLineSplits: vi.fn(),
}));
vi.mock('@/app/(protected)/project-sales/_shared/services/lineSplitService', () => ({
  getLineSplits: (...a: unknown[]) => getLineSplits(...a),
  saveLineSplits: (...a: unknown[]) => saveLineSplits(...a),
}));
vi.mock('@/lib/toast', () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), warning: vi.fn() }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  getLineSplits.mockResolvedValue(structuredClone(savedCase()));
  saveLineSplits.mockResolvedValue(structuredClone(savedCase()));
});

// `onlyLineIds` is the new prop (contract with the coder); the kit's props type predates it.
const scoped = (ids: string[]) =>
  renderDialog({ onlyLineIds: new Set(ids) } as unknown as Parameters<typeof renderDialog>[0]);

describe('F13: the scoped edit sheet', () => {
  it('lists only the covered line and the line its saved split sits on, never the rest of the order', async () => {
    await scoped(['L480']);
    await sheet();
    // 480's 236 sits on 608: both are shown; 752, 768 and 900 are not.
    expect(blockIds()).toEqual(['split-line-480', 'split-line-608']);
  });

  it('a covered line with no split lists just itself', async () => {
    await scoped(['L752']);
    await sheet();
    expect(blockIds()).toEqual(['split-line-752']);
  });

  it('has no "Split lines only" toggle and no search box', async () => {
    await scoped(['L480']);
    await sheet();
    expect(screen.queryByText('Split lines only')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/item code/i)).not.toBeInTheDocument();
  });

  it('pin: without the prop (the board gear) every line is listed and the toggle and search are there', async () => {
    await renderDialog();
    await sheet();
    expect(blockIds()).toHaveLength(5);
    expect(screen.getByText('Split lines only')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/item code/i)).toBeInTheDocument();
  });

  it('F16: the header count reads the shown lines only', async () => {
    await scoped(['L480']);
    await sheet();
    expect(screen.getByText(/^2 lines · /)).toBeInTheDocument();
    expect(screen.queryByText(/^5 lines/)).not.toBeInTheDocument();
  });

  it('F16 pin: unscoped the header counts every line', async () => {
    await renderDialog();
    await sheet();
    expect(screen.getByText(/^5 lines · /)).toBeInTheDocument();
  });

  it('F16: a problem on a hidden line is never named; unscoped it is', async () => {
    const withProblem = () => {
      const p = structuredClone(savedCase());
      // Line 900 (hidden when scoped to 480): 20 of 50 planned, so 30 are left.
      p.lines.find((l) => l.line_id === 'L900')!.splits = [wireSplit('h1', 20, '2026-10-01', 'L900')];
      return p;
    };
    getLineSplits.mockResolvedValue(withProblem());
    await scoped(['L480']);
    await sheet();
    expect(screen.queryByText(/30 left/)).not.toBeInTheDocument();
    cleanup();
    getLineSplits.mockResolvedValue(withProblem());
    await renderDialog();
    await sheet();
    expect(screen.getByText(/line 900: 30 left/)).toBeInTheDocument();
  });
});

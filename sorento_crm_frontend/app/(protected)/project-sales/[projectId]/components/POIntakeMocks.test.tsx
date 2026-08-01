/**
 * P4 / P5 - the toggleable fixtures.
 *
 * They exist so every state can be looked at while the backend is still being written, which
 * only helps if the fixtures are COHERENT: the sums add up, the short read is short, and
 * accepting a card actually moves the lines it names.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { resolveExtractionPhase } from '../../_shared/types/poIntake.types';
import { formatMyrExact, sumMoney } from './POIntakeMoney';
import { isPOMockScenario, mockVersion, usePOIntakeMockController } from './POIntakeMocks';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

describe('PO intake mock scenarios', () => {
  it('only accepts scenarios it knows', () => {
    expect(isPOMockScenario('partial')).toBe(true);
    expect(isPOMockScenario('nonsense')).toBe(false);
    expect(isPOMockScenario(null)).toBe(false);
  });

  it('reads the real PO: 52 lines, 10 pages, totals that add up', () => {
    const version = mockVersion('done');

    expect(version.lines).toHaveLength(52);
    expect(version.page_count).toBe(10);
    expect(version.header.po_number).toBe('HQ/26/01/041');
    expect(version.header.admin_ref).toBe('PS26-0143');
    expect(version.lines[0].amount).toBe('364171.95');
    expect(sumMoney(version.lines.map((l) => l.amount))).toBe(version.totals.lines_total);
    expect(version.totals.extracted_total).toBe(version.totals.lines_total);
    expect(resolveExtractionPhase(version)).toBe('done');
  });

  it('makes the partial read genuinely short, and short in money too', () => {
    const version = mockVersion('partial');

    expect(resolveExtractionPhase(version)).toBe('partial');
    expect(version.pages_extracted).toBe(7);
    expect(version.failed_pages).toEqual([8, 9, 10]);
    expect(version.lines.length).toBeLessThan(52);
    expect(formatMyrExact(version.totals.extracted_total)).toBe('RM 1,810,640.62');
    expect(version.totals.lines_total).not.toBe(version.totals.extracted_total);
  });

  it('makes the mismatch one misread amount rather than a broken document', () => {
    const version = mockVersion('mismatch');

    expect(version.totals.arithmetic_passed).toBe(51);
    expect(version.totals.arithmetic_total).toBe(52);
    expect(version.totals.lines_total).not.toBe(version.totals.extracted_total);
  });

  it('carries the two real amendments plus a signature, all unreviewed', () => {
    const version = mockVersion('done');
    const proposed = version.annotations.filter((note) => note.state === 'proposed');

    expect(proposed).toHaveLength(4);
    expect(version.annotations.map((note) => note.interpretation)).toEqual([
      'cancel_line',
      'successor_po',
      'amend_code',
      'signature',
    ]);
  });

  it('applies an accepted cancellation to the line it names and drops it from the total', () => {
    const { result } = renderHook(() => usePOIntakeMockController('done'));
    const before = result.current.version?.totals.lines_total;

    act(() => {
      void result.current.acceptAnnotation('mock-annot-1');
    });

    const line7 = result.current.version?.lines.find((line) => line.line_no === 7);
    expect(line7?.is_cancelled).toBe(true);
    expect(result.current.version?.annotations[0].state).toBe('accepted');
    expect(result.current.version?.totals.lines_total).not.toBe(before);
  });

  it("applies the human's reading when a card is edited", () => {
    const { result } = renderHook(() => usePOIntakeMockController('done'));

    act(() => {
      void result.current.editAnnotation('mock-annot-3', {
        interpretation: 'amend_code',
        interpretation_json: { line_nos: [5], code: 'SRTMX3300-BK' },
        note: 'Only line 5 is legible',
      });
    });

    const lines = result.current.version?.lines ?? [];
    expect(lines.find((line) => line.line_no === 5)?.stock_code_raw).toBe('SRTMX3300-BK');
    expect(lines.find((line) => line.line_no === 20)?.stock_code_raw).not.toBe(
      'SRTMX3300-BK',
    );
    expect(result.current.version?.annotations[2].state).toBe('edited');
  });

  it('applies nothing at all when a card is rejected', () => {
    const { result } = renderHook(() => usePOIntakeMockController('done'));

    act(() => {
      void result.current.rejectAnnotation('mock-annot-1', 'Not an amendment');
    });

    expect(result.current.version?.lines.find((l) => l.line_no === 7)?.is_cancelled).toBe(
      false,
    );
    expect(result.current.version?.annotations[0].state).toBe('rejected');
    expect(result.current.version?.annotations[0].action_note).toBe('Not an amendment');
  });

  it('recomputes a line the way the backend would after an edit', () => {
    const { result } = renderHook(() => usePOIntakeMockController('done'));

    act(() => {
      void result.current.updateLine('mock-line-1', { qty: '900' });
    });

    const line = result.current.version?.lines[0];
    expect(line?.qty).toBe('900');
    // 900 x 392.85 is 353,565.00, so the untouched amount no longer multiplies out.
    expect(line?.arithmetic_ok).toBe(false);

    act(() => {
      void result.current.updateLine('mock-line-1', { amount: '353565.00' });
    });
    expect(result.current.version?.lines[0].arithmetic_ok).toBe(true);
  });

  it('says out loud that it is a mock', () => {
    const { result } = renderHook(() => usePOIntakeMockController('done'));
    expect(result.current.isMock).toBe(true);
    expect(result.current.isLoading).toBe(false);
  });
});

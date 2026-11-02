/**
 * PRICING-UX-FIXES A: a draft line is judged against the series the editor holds, so a scope not
 * saved yet (no quotation id) and a saved one with a series change staged both get live alerts.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import { judgeQuotationLine } from './projectService';

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ ok: true, json: async () => ({ is_below_floor: false }) });
});

const calledUrl = () => String(apiFetch.mock.calls[0][0]);

describe('judgeQuotationLine', () => {
  it('asks by series on a scope with no quotation id yet', async () => {
    await judgeQuotationLine({ quotationId: null, seriesId: 's1' }, { product_id: 'p1', unit_price: '80' });
    const url = calledUrl();
    expect(url.startsWith('/api/v1/project-sales/quotation-line-verdict?')).toBe(true);
    expect(url).toContain('series_id=s1');
    expect(url).toContain('product_id=p1');
    expect(url).toContain('unit_price=80');
  });

  it('asks by the editor series on a saved scope too, so a staged series change counts', async () => {
    await judgeQuotationLine({ quotationId: 'q1', seriesId: 's2' }, { product_id: 'p1' });
    expect(calledUrl()).toContain('/quotation-line-verdict?');
    expect(calledUrl()).toContain('series_id=s2');
    expect(calledUrl()).not.toContain('/quotations/q1/');
  });

  it('asks with no series when the scope has none', async () => {
    await judgeQuotationLine({ quotationId: null, seriesId: null }, { product_id: 'p1' });
    expect(calledUrl()).toContain('/quotation-line-verdict?');
    expect(calledUrl()).not.toContain('series_id');
  });

  it('asks by quotation only when the caller names no series at all', async () => {
    await judgeQuotationLine({ quotationId: 'q1' }, { product_id: 'p1' });
    expect(calledUrl()).toContain('/quotations/q1/line-verdict');
  });
});

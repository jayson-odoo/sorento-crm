/**
 * SCM Coverage Timeline feature service (UAC Group B).
 *
 * Two things are pinned here, because they are the two things Phase 2 flips:
 *
 *  1) The MOCK branch, which is what Phase 1 actually runs: `USE_COVERAGE_MOCKS`
 *     true must serve the fixture and make NO request. A mock branch that quietly
 *     calls the backend is the failure this catches.
 *  2) The REAL branch's request shape - flat `/api/v1/scm/coverage`, the three
 *     human-code params, and `extractApiError` on a non-ok response. It is
 *     unreachable while the flag is on, so nothing but a test can prove it right
 *     before the flag flips.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

// The flag lives in the mock store; the store is deleted in Phase 2, so both
// branches are exercised by controlling it here rather than by editing source.
const mockStore = vi.hoisted(() => ({
  USE_COVERAGE_MOCKS: true,
  mockCoverageTimeline: vi.fn(),
  mockAcceptTransfer: vi.fn(),
}));
vi.mock('../lib/coverageMockStore', () => mockStore);

import { acceptCoverageTransfer, getCoverageTimeline } from './coverageService';

function ok(body: unknown) {
  return {
    ok: true,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}
function fail(detail: string, status = 404) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}
function calledUrl(): URL {
  const calls = apiFetch.mock.calls;
  return new URL(String(calls[calls.length - 1][0]), 'http://x');
}

beforeEach(() => {
  apiFetch.mockReset();
  mockStore.mockCoverageTimeline.mockReset();
  mockStore.mockAcceptTransfer.mockReset();
  mockStore.USE_COVERAGE_MOCKS = true;
});

describe('coverageService - Phase-1 mock branch', () => {
  it('serves the fixture and never touches the network', async () => {
    mockStore.mockCoverageTimeline.mockResolvedValue({ product_code: 'SRTWT7408' });
    const out = await getCoverageTimeline({
      product_code: 'SRTWT7408',
      pool_code: 'BRW',
      floor: 0,
      product_name: 'Wall-hung WC 7408',
    });
    expect(out).toEqual({ product_code: 'SRTWT7408' });
    expect(mockStore.mockCoverageTimeline).toHaveBeenCalledWith('SRTWT7408', 'Wall-hung WC 7408');
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('serves the mocked transfer acceptance', async () => {
    mockStore.mockAcceptTransfer.mockResolvedValue({
      proposal_ref: 'TP-MWH-0001',
      accepted: true,
      transfer_ref: 'TRF-2026-0087',
    });
    const out = await acceptCoverageTransfer('TP-MWH-0001');
    expect(out.transfer_ref).toBe('TRF-2026-0087');
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

describe('coverageService - Phase-2 real branch', () => {
  beforeEach(() => {
    mockStore.USE_COVERAGE_MOCKS = false;
  });

  it('GETs the flat /scm/coverage route with product_code, pool_code and floor', async () => {
    apiFetch.mockResolvedValue(ok({ product_code: 'SRTBS4832', pool_code: 'BRW' }));
    await getCoverageTimeline({ product_code: 'SRTBS4832', pool_code: 'BRW-BB', floor: 12 });

    const url = calledUrl();
    // Flat under /scm/, like every other SCM route - no nested reorder/ segment.
    expect(url.pathname).toBe('/api/v1/scm/coverage');
    expect(url.searchParams.get('product_code')).toBe('SRTBS4832');
    expect(url.searchParams.get('pool_code')).toBe('BRW-BB');
    expect(url.searchParams.get('floor')).toBe('12');
    // Human codes only: no id of any kind is sent.
    expect(url.search).not.toMatch(/product_id|pool_id|warehouse_id/);
  });

  it('sends floor=0 rather than omitting it, so the server never has to guess', async () => {
    apiFetch.mockResolvedValue(ok({}));
    await getCoverageTimeline({ product_code: 'X', pool_code: 'DC1', floor: 0 });
    expect(calledUrl().searchParams.get('floor')).toBe('0');
  });

  it('throws the extracted backend message when the timeline cannot be computed', async () => {
    apiFetch.mockResolvedValue(fail('Unknown pool code BRW-ZZ'));
    await expect(
      getCoverageTimeline({ product_code: 'X', pool_code: 'BRW-ZZ', floor: 0 }),
    ).rejects.toThrow('Unknown pool code BRW-ZZ');
  });

  it('POSTs the transfer acceptance to the proposal_ref route', async () => {
    apiFetch.mockResolvedValue(
      ok({ proposal_ref: 'TP-MWH-0001', accepted: true, transfer_ref: 'TRF-1' }),
    );
    await acceptCoverageTransfer('TP-MWH-0001');
    expect(calledUrl().pathname).toBe(
      '/api/v1/scm/coverage/transfer-proposals/TP-MWH-0001/accept',
    );
    expect((apiFetch.mock.calls[0][1] as RequestInit).method).toBe('POST');
  });

  it('throws the extracted message when the acceptance is refused', async () => {
    apiFetch.mockResolvedValue(fail('Proposal already accepted', 409));
    await expect(acceptCoverageTransfer('TP-MWH-0001')).rejects.toThrow(
      'Proposal already accepted',
    );
  });
});

/**
 * PS-SAMPLE-TRACKING (crew browser pass, AC-ST-04): the salesperson's own list carries the date
 * shown, the sample team's proposed one with the New date flag when it gave one.
 */
import { describe, expect, it } from 'vitest';
import { makeSampleRequestService } from './sample-request-service';

function row(over: Record<string, unknown>) {
  return {
    id: 'r-1',
    request_no: 'SR-000001',
    status: 'processing',
    status_label: 'Processing',
    request_date: '2026-11-02',
    customer_name: 'Acme',
    project_name: 'Tower',
    delivery_date: '2026-12-01',
    date_feasible: null,
    proposed_delivery_date: null,
    ...over,
  };
}

function serviceReturning(rows: unknown[]) {
  const fetcher = async () =>
    new Response(JSON.stringify({ data: rows }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  return makeSampleRequestService(fetcher as never);
}

describe('portal sample request summaries', () => {
  it('carries the proposed date flagged new, else the requested date', async () => {
    const svc = serviceReturning([
      row({ id: 'a', date_feasible: false, proposed_delivery_date: '2026-12-09' }),
      row({ id: 'b', date_feasible: true }),
    ]);
    const [proposed, met] = await svc.listSampleRequestsAsSummaries();
    expect(proposed).toMatchObject({ delivery_date: '2026-12-09', delivery_date_is_new: true });
    expect(met).toMatchObject({ delivery_date: '2026-12-01', delivery_date_is_new: false });
  });
});

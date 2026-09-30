/**
 * autocountPullService - Delivery Orders additions (lane DO-PULL-CRM, AC-DP-02b).
 *
 * The DO-PULL-SS snapshot answers 409 `BUILD_IN_FLIGHT` when a build with a DIFFERENT scope
 * is still running for the company; the start-error map must say so in one line (AC-PL-6's
 * rule: every known code gets its own distinct message). Same harness as
 * `autocountPullService.test.ts`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { startPull, startPullErrorMessage } from './autocountPullService';

function fail(status: number, body: unknown) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
    clone() {
      return fail(status, body);
    },
  } as unknown as Response;
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('startPullErrorMessage - BUILD_IN_FLIGHT (AC-DP-02b)', () => {
  it('maps the 409 to its own sentence, distinct from every other start refusal', async () => {
    apiFetch.mockResolvedValue(
      fail(409, { code: 'BUILD_IN_FLIGHT', message: 'A build with a different scope is in flight.' }),
    );
    let caught: unknown;
    try {
      await startPull('delivery_orders');
    } catch (error) {
      caught = error;
    }
    const message = startPullErrorMessage(caught);
    expect(message).toMatch(/different scope/i);
    expect(message).not.toBe(startPullErrorMessage({ code: 'TOO_MANY_BUILDS' }));
    expect(message).not.toBe(startPullErrorMessage({ code: 'PUSH_ACTIVE' }));
  });

  it('posts the entity alone when no scope is given (the 31-day default)', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ job_id: 'j', entity: 'delivery_orders', phase: 'building' }),
    } as unknown as Response);
    await startPull('delivery_orders');
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/autocount/pulls');
    expect(JSON.parse(String(init.body))).toEqual({ entity: 'delivery_orders' });
  });
});

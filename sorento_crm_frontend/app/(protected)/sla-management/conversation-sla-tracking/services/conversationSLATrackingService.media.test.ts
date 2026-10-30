/**
 * QUOTE-DRAWING-ESCALATE rework: the assignee's Respond / Resolve on a product drawing or photo
 * task reach the shared `media-respond` / `media-resolve` routes (one route pair for both kinds).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { actOnDrawingRequest } from './conversationSLATrackingService';

beforeEach(() => apiFetch.mockReset());

describe('actOnDrawingRequest (media tasks)', () => {
  it.each(['respond', 'resolve'] as const)('POSTs the media-%s route', async (action) => {
    apiFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });

    await actOnDrawingRequest('trk-1', action);

    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/v1/sla-management/form-sla-tracking/trk-1/media-${action}`);
    expect(init.method).toBe('POST');
  });

  it('surfaces the server message when refused', async () => {
    apiFetch.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Not yours' }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      }),
    );
    await expect(actOnDrawingRequest('trk-1', 'respond')).rejects.toThrow('Not yours');
  });
});

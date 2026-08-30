/**
 * The deferred-action service against the real routes (Phase 2).
 *
 * Phase 1 answered these three calls from an in-memory stand-in that chose the
 * window itself, by the verb in the key. That rule now lives on the SERVER, where
 * it can read the two System Settings columns (S6-04), so what this file pins is
 * the seam: the request shape each route expects, and that the countdown's
 * `window_seconds` and `commit_at` come back from the response rather than being
 * decided here. A client that recomputed either would drift from the clock that
 * actually applies the action.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  cancelPendingAction,
  createPendingAction,
  getCurrentPendingAction,
} from './pendingActionService';

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

function fail(message: string, status = 409) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ message }),
    text: async () => JSON.stringify({ message }),
  } as unknown as Response;
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('createPendingAction', () => {
  it('posts the four fields the route reads and nothing else', async () => {
    apiFetch.mockResolvedValue(
      ok({ id: 'pa-1', commit_at: '2026-08-30T10:00:10', window_seconds: 10 }),
    );

    await createPendingAction({
      actionKey: 'order.set_status',
      entityType: 'order',
      entityId: 'o-1',
      payload: { order_status_id: 's-2' },
    });

    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/pending-actions');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      action_key: 'order.set_status',
      entity_type: 'order',
      entity_id: 'o-1',
      payload: { order_status_id: 's-2' },
    });
  });

  it('sends an empty payload rather than none when the action needs no arguments', async () => {
    apiFetch.mockResolvedValue(
      ok({ id: 'pa-1', commit_at: '2026-08-30T10:00:10', window_seconds: 10 }),
    );

    await createPendingAction({
      actionKey: 'product.delete',
      entityType: 'product',
      entityId: 'p-1',
    });

    expect(JSON.parse(apiFetch.mock.calls[0][1].body).payload).toEqual({});
  });

  it('takes the window and the deadline from the SERVER, not from the key', async () => {
    // A ten-second delete would be the frontend's guess; the admin set five.
    apiFetch.mockResolvedValue(
      ok({ id: 'pa-1', commit_at: '2026-08-30T10:00:05', window_seconds: 5 }),
    );

    const action = await createPendingAction({
      actionKey: 'product.delete',
      entityType: 'product',
      entityId: 'p-1',
    });

    expect(action).toEqual({
      id: 'pa-1',
      action_key: 'product.delete',
      entity_type: 'product',
      entity_id: 'p-1',
      commit_at: '2026-08-30T10:00:05',
      window_seconds: 5,
    });
  });

  it('surfaces the server refusal when a record is already counting down', async () => {
    apiFetch.mockResolvedValue(
      fail('Another action on this record is still counting down.'),
    );

    await expect(
      createPendingAction({
        actionKey: 'order.delete',
        entityType: 'order',
        entityId: 'o-1',
      }),
    ).rejects.toThrow('Another action on this record is still counting down.');
  });
});

describe('cancelPendingAction', () => {
  it('posts to the action\'s own cancel route', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'pa-1', status: 'cancelled' }));

    await cancelPendingAction('pa-1');

    expect(apiFetch).toHaveBeenCalledWith('/api/v1/pending-actions/pa-1/cancel', {
      method: 'POST',
    });
  });

  it('reports a cancel that arrived after the window closed', async () => {
    apiFetch.mockResolvedValue(fail('That action has already been applied.'));

    await expect(cancelPendingAction('pa-1')).rejects.toThrow(
      'That action has already been applied.',
    );
  });
});

describe('getCurrentPendingAction', () => {
  it('asks for one record and returns both halves of the answer', async () => {
    apiFetch.mockResolvedValue(
      ok({
        pending: null,
        last_outcome: {
          id: 'pa-1',
          action_key: 'product.delete',
          status: 'failed',
          error_text: 'The warehouse still holds stock for it',
          ended_at: '2026-08-30T10:00:10',
        },
      }),
    );

    const body = await getCurrentPendingAction('product', 'p-1');

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/pending-actions/current?entity_type=product&entity_id=p-1',
    );
    expect(body.pending).toBeNull();
    // The half that stops a failure reading as a success.
    expect(body.last_outcome?.status).toBe('failed');
    expect(body.last_outcome?.action_key).toBe('product.delete');
  });
});

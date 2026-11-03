/**
 * CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): a stale tab never posts an older decision over a
 * newer save. A saved decision is never compared with AutoCount's suggestion (NO-AC-MOVED-WARNING).
 */
import { describe, expect, it } from 'vitest';
import { emailPreviewBody, newerServerDraftKeys, queuedPerKey } from './confirmPreviewFresh';

const draftAt = (key: string, savedAt: string) => ({
  key,
  draft: { decision: { verdict: 'approved' as const }, saved_by: 'Test Planner', saved_at: savedAt },
});

describe('newerServerDraftKeys', () => {
  const local = { a: { verdict: 'approved' as const }, b: { verdict: 'approved' as const } };

  it('names a key whose server draft was saved after the one this tab holds', () => {
    const held = new Map([['a', '2026-11-02T01:00:00Z']]);
    expect([...newerServerDraftKeys(local, held, [draftAt('a', '2026-11-02T02:00:00Z')])]).toEqual(['a']);
  });

  it('leaves the same or an older save alone', () => {
    const held = new Map([['a', '2026-11-02T02:00:00Z']]);
    expect(newerServerDraftKeys(local, held, [draftAt('a', '2026-11-02T02:00:00Z')]).size).toBe(0);
    expect(newerServerDraftKeys(local, held, [draftAt('a', '2026-11-02T01:00:00Z')]).size).toBe(0);
  });

  it('leaves a pre-mark, a key with no record and a key mid-write alone', () => {
    const held = new Map([['a', '2026-11-02T01:00:00Z']]);
    const later = [draftAt('a', '2026-11-02T02:00:00Z'), draftAt('b', '2026-11-02T02:00:00Z')];
    expect(
      newerServerDraftKeys({ a: { verdict: 'approved', preMarked: true } }, held, later).size,
    ).toBe(0);
    expect(newerServerDraftKeys(local, held, later, (key) => key === 'a').size).toBe(0);
    expect([...newerServerDraftKeys(local, held, later)]).toEqual(['a']);
  });
});

describe('queuedPerKey', () => {
  it('a second task on one key starts only after the first settles; other keys do not wait', async () => {
    const queue = new Map<string, Promise<void>>();
    const order: string[] = [];
    let release: () => void = () => {};
    const first = queuedPerKey(queue, 'a', () => new Promise<void>((resolve) => {
      order.push('a1 start');
      release = () => {
        order.push('a1 end');
        resolve();
      };
    }));
    const second = queuedPerKey(queue, 'a', async () => {
      order.push('a2 start');
    });
    const other = queuedPerKey(queue, 'b', async () => {
      order.push('b start');
    });
    await other;
    await Promise.resolve();
    expect(order).toEqual(['a1 start', 'b start']);
    release();
    await first;
    await second;
    expect(order).toEqual(['a1 start', 'b start', 'a1 end', 'a2 start']);
    expect(queue.size).toBe(0);
  });

  it('a failed task still lets the next one run, and onIdle runs once, after the last', async () => {
    const queue = new Map<string, Promise<void>>();
    const idle: string[] = [];
    const failing = queuedPerKey(queue, 'a', async () => {
      throw new Error('refused');
    }, () => idle.push('idle'));
    const next = queuedPerKey(queue, 'a', async () => 'ran', () => idle.push('idle'));
    await expect(failing).rejects.toThrow('refused');
    await expect(next).resolves.toBe('ran');
    expect(idle).toEqual(['idle']);
  });
});

describe('emailPreviewBody (review round 3, S3)', () => {
  const order = (pso_id: string) => ({ pso_id, lines: [] }) as never;

  it('is quiet, and leaves out an order with no planning record yet', () => {
    const body = emailPreviewBody({ orders: [order('pso-1'), order('')] } as never);
    expect(body?.quiet).toBe(true);
    expect(body?.orders.map((o) => o.pso_id)).toEqual(['pso-1']);
  });

  it('is null when nothing is left to preview', () => {
    expect(emailPreviewBody({ orders: [order('')] } as never)).toBeNull();
    expect(emailPreviewBody(null)).toBeNull();
  });
});

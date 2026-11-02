import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { POLL_CAP_MINUTES, pollIntervalFor, shouldPollBackend } from './pollCap';
import type { UploadActivitySession } from './types';

const NOW = Date.parse('2026-11-02T12:00:00Z');

// The naive-UTC test only bites off UTC: a local parse in UTC+8 shifts every timestamp 8 hours.
const previousTz = process.env.TZ;
beforeAll(() => {
  process.env.TZ = 'Asia/Kuala_Lumpur';
});
afterAll(() => {
  if (previousTz === undefined) delete process.env.TZ;
  else process.env.TZ = previousTz;
});

function session(
  status: UploadActivitySession['status'],
  minutesAgo: number,
  naive = true,
  type: UploadActivitySession['session_type'] = 'single',
): UploadActivitySession {
  // The backend emits naive UTC (`datetime.utcnow()`); timeUtil.parseServerDate anchors it.
  const iso = new Date(NOW - minutesAgo * 60_000).toISOString();
  return {
    session_id: `s-${status}-${minutesAgo}`,
    session_type: type,
    title: 'brochure.pdf',
    started_at: naive ? iso.replace('Z', '') : iso,
    finished_at: null,
    status,
    aggregate: { total: 1, uploading: 0, processing: 1, linked: 0, unlinked: 0, failed: 0 },
    files: [],
    import_job_id: null,
    needs_action: false,
  };
}

describe('shouldPollBackend (INTEGRATION-LOG-INDEXES polling cap)', () => {
  it('caps at 30 minutes', () => {
    expect(POLL_CAP_MINUTES).toBe(30);
  });

  it('polls for a processing session younger than the cap', () => {
    expect(shouldPollBackend([session('processing', 2)], NOW)).toBe(true);
    expect(shouldPollBackend([session('uploading', 29)], NOW)).toBe(true);
  });

  it('stops for a session stuck processing longer than the cap', () => {
    expect(shouldPollBackend([session('processing', 31)], NOW)).toBe(false);
    expect(shouldPollBackend([session('processing', 60 * 24 * 3)], NOW)).toBe(false);
  });

  it('reads the naive server timestamp as UTC, not local time', () => {
    expect(new Date('2026-11-02T12:00:00').getTimezoneOffset()).toBe(-480);
    // In UTC+8 a local parse would make a 2-minute-old upload look 8 hours old.
    expect(shouldPollBackend([session('processing', 2, true)], NOW)).toBe(true);
    expect(shouldPollBackend([session('processing', 2, false)], NOW)).toBe(true);
  });

  it('keeps polling while any fresh session is in flight next to a stuck one', () => {
    expect(
      shouldPollBackend([session('processing', 500), session('processing', 1)], NOW),
    ).toBe(true);
  });

  it('never polls for terminal sessions', () => {
    expect(
      shouldPollBackend([session('linked', 1), session('failed', 1), session('partial', 1)], NOW),
    ).toBe(false);
    expect(shouldPollBackend([], NOW)).toBe(false);
  });

  it('does not cap import jobs: an RQ import can run past 30 minutes', () => {
    expect(shouldPollBackend([session('processing', 90, true, 'import_job')], NOW)).toBe(true);
  });
});

describe('pollIntervalFor (the bell query refetchInterval)', () => {
  it('polls every 5 s while an optimistic upload is in flight, even next to a stuck one', () => {
    expect(pollIntervalFor([session('processing', 500)], true, NOW)).toBe(5_000);
    expect(pollIntervalFor(undefined, true, NOW)).toBe(5_000);
  });

  it('follows the capped backend check otherwise', () => {
    expect(pollIntervalFor([session('processing', 2)], false, NOW)).toBe(5_000);
    expect(pollIntervalFor([session('processing', 500)], false, NOW)).toBe(false);
    expect(pollIntervalFor(undefined, false, NOW)).toBe(false);
  });
});

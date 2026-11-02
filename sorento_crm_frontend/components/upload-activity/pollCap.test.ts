import { describe, expect, it } from 'vitest';

import { POLL_CAP_MINUTES, shouldPollBackend } from './pollCap';
import type { UploadActivitySession } from './types';

const NOW = Date.parse('2026-11-02T12:00:00Z');

function session(
  status: UploadActivitySession['status'],
  minutesAgo: number,
  naive = true,
): UploadActivitySession {
  // The backend emits naive UTC (`datetime.utcnow()`); timeUtil.parseServerDate anchors it.
  const iso = new Date(NOW - minutesAgo * 60_000).toISOString();
  return {
    session_id: `s-${status}-${minutesAgo}`,
    session_type: 'single',
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
});

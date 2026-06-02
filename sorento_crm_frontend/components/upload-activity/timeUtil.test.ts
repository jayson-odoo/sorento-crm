import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { parseServerDate, timeAgo } from './timeUtil';

describe('parseServerDate', () => {
  it('treats naive ISO (no tz suffix) as UTC', () => {
    // Bare string → Z appended → exactly 2026-06-02T10:00:00Z.
    const d = parseServerDate('2026-06-02T10:00:00');
    expect(d.toISOString()).toBe('2026-06-02T10:00:00.000Z');
  });

  it('honours an explicit Z suffix', () => {
    const d = parseServerDate('2026-06-02T10:00:00Z');
    expect(d.toISOString()).toBe('2026-06-02T10:00:00.000Z');
  });

  it('honours explicit +HH:MM offsets', () => {
    const d = parseServerDate('2026-06-02T18:00:00+08:00');
    expect(d.toISOString()).toBe('2026-06-02T10:00:00.000Z');
  });
});

describe('timeAgo', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-02T10:00:00Z'));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "just now" for a naive timestamp at the same UTC moment', () => {
    // Regression: previously "8 hr ago" because parsed as local UTC+8.
    expect(timeAgo('2026-06-02T10:00:00')).toBe('just now');
  });

  it('shows minutes when within the hour', () => {
    expect(timeAgo('2026-06-02T09:55:00')).toBe('5 min ago');
  });

  it('shows hours past the hour boundary', () => {
    expect(timeAgo('2026-06-02T07:00:00')).toBe('3 hr ago');
  });
});

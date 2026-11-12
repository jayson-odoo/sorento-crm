/**
 * DATE-PICKER-UNIFY AC6: the API sends activity timestamps as naive UTC (no `Z`). `new Date(iso)`
 * reads such a string as LOCAL time, so in Malaysia (UTC+8) a one-minute-old row read "8h ago".
 */
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { relativeTime } from './EntityActivitiesLayout';

const originalTz = process.env.TZ;

beforeAll(() => {
  process.env.TZ = 'Asia/Kuala_Lumpur';
});

afterAll(() => {
  if (originalTz === undefined) delete process.env.TZ;
  else process.env.TZ = originalTz;
});

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-05T02:00:00Z'));
});

afterEach(() => {
  vi.useRealTimers();
});

describe('relativeTime', () => {
  it('reads a naive UTC timestamp one minute old as 1m ago', () => {
    expect(relativeTime('2026-11-05T01:59:00')).toBe('1m ago');
  });

  it('reads a Z-suffixed timestamp one minute old as 1m ago', () => {
    expect(relativeTime('2026-11-05T01:59:00Z')).toBe('1m ago');
  });

  it('reads a naive UTC timestamp two hours old as 2h ago', () => {
    expect(relativeTime('2026-11-05T00:00:00')).toBe('2h ago');
  });
});

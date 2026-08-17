import { describe, expect, it } from 'vitest';
import { describeReadingTime, formatReadingTime } from './readingTime';

describe('formatReadingTime', () => {
  it('says nothing when there is no measurement', () => {
    // Documents read before the duration was recorded carry null, and inventing a
    // number for them would be worse than the blank.
    expect(formatReadingTime(null)).toBeNull();
    expect(formatReadingTime(undefined)).toBeNull();
    expect(formatReadingTime(0)).toBeNull();
    expect(formatReadingTime(-5)).toBeNull();
    expect(formatReadingTime(Number.NaN)).toBeNull();
  });

  it('never rounds a real read down to nothing', () => {
    expect(formatReadingTime(120)).toBe('under a second');
  });

  it('reads seconds under a minute', () => {
    expect(formatReadingTime(1_000)).toBe('1s');
    expect(formatReadingTime(45_400)).toBe('45s');
    expect(formatReadingTime(59_400)).toBe('59s');
  });

  it('rolls over to minutes at sixty seconds', () => {
    expect(formatReadingTime(60_000)).toBe('1m');
    expect(formatReadingTime(134_812)).toBe('2m 15s');
    expect(formatReadingTime(600_000)).toBe('10m');
  });

  it('describes the duration as a caption', () => {
    expect(describeReadingTime(134_812)).toBe('Read in 2m 15s');
    expect(describeReadingTime(null)).toBeNull();
  });
});

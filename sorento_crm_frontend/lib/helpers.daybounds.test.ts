/**
 * DATE-PICKER-UNIFY AC11: a whole Malaysia day (UTC+8) as UTC ISO bounds, for date-time filter
 * params. Independent of the browser timezone.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import * as helpers from './helpers';

const { malaysiaDayStartIso, malaysiaDayEndIso } = helpers as unknown as {
  malaysiaDayStartIso: (day: string | null | undefined) => string | undefined;
  malaysiaDayEndIso: (day: string | null | undefined) => string | undefined;
};

describe.each(['default', 'America/New_York', 'UTC'])('Malaysia day bounds under TZ %s', (zone) => {
  const original = process.env.TZ;
  beforeAll(() => {
    if (zone !== 'default') process.env.TZ = zone;
  });
  afterAll(() => {
    if (original === undefined) delete process.env.TZ;
    else process.env.TZ = original;
  });

  it('malaysiaDayStartIso("2026-11-05") is 2026-11-04T16:00:00.000Z', () => {
    expect(malaysiaDayStartIso('2026-11-05')).toBe('2026-11-04T16:00:00.000Z');
  });

  it('malaysiaDayEndIso("2026-11-05") is 2026-11-05T15:59:59.999Z', () => {
    expect(malaysiaDayEndIso('2026-11-05')).toBe('2026-11-05T15:59:59.999Z');
  });

  it('both return undefined for null, empty and a day that does not exist', () => {
    for (const bad of [null, '', '2026-02-31']) {
      expect(malaysiaDayStartIso(bad)).toBeUndefined();
      expect(malaysiaDayEndIso(bad)).toBeUndefined();
    }
  });
});

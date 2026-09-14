/**
 * The auto-collect setting reaches the FE (r9 S3/D10, AC-S3-7).
 *
 * LESSONS: a new settings column reaches the frontend only if it is in the
 * MANUAL mapper too. `mapSettingsFromApi` in `layout.tsx` is that mapper, and a
 * column missing from it looks exactly like a backend that never saved the
 * value.
 *
 * RED before the coder starts on two counts: the mapper is not exported, and
 * while the column does not exist Phase 1 falls back to a per-tab override
 * (`readAutoCollectDaysOverride`) that must go with it - a real answer of 0
 * ("the sweep is off") is falsy, and an override consulted after the column
 * lands would quietly overwrite it.
 */
import { describe, it, expect, beforeEach } from 'vitest';

import {
  AUTO_COLLECT_DAYS_DEFAULT,
  _resetCollectionOverrides,
  setAutoCollectDaysOverride,
} from '@/lib/dealer-kit/print-collection';
import { mapSettingsFromApi } from './layout';

beforeEach(() => {
  _resetCollectionOverrides();
});

describe('mapSettingsFromApi (AC-S3-7)', () => {
  it('carries the auto-collect days the server sent', () => {
    const mapped = mapSettingsFromApi({
      name: 'ZZT Co',
      price_tag_auto_collect_days: 14,
    } as never);

    expect(mapped.priceTagAutoCollectDays).toBe(14);
  });

  it('keeps 0, which means the sweep is off and is NOT "no answer"', () => {
    const mapped = mapSettingsFromApi({
      name: 'ZZT Co',
      price_tag_auto_collect_days: 0,
    } as never);

    expect(mapped.priceTagAutoCollectDays).toBe(0);
  });

  it('falls back to the shipped default when the row predates the column', () => {
    const mapped = mapSettingsFromApi({ name: 'ZZT Co' } as never);

    expect(mapped.priceTagAutoCollectDays).toBe(AUTO_COLLECT_DAYS_DEFAULT);
  });

  it('never consults the Phase 1 per-tab override', () => {
    setAutoCollectDaysOverride(30);

    const withValue = mapSettingsFromApi({
      name: 'ZZT Co',
      price_tag_auto_collect_days: 5,
    } as never);
    const withoutValue = mapSettingsFromApi({ name: 'ZZT Co' } as never);

    expect(withValue.priceTagAutoCollectDays).toBe(5);
    expect(withoutValue.priceTagAutoCollectDays).toBe(AUTO_COLLECT_DAYS_DEFAULT);
  });
});

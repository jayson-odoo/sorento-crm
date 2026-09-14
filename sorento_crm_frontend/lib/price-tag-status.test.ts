/**
 * The status vocabulary after `ready` is retired (r9 S3/D8, AC-S3-3).
 *
 * `ready` said a PDF existed. Nothing about it said anybody had the tags, and
 * the migration maps every row that carried it to `approved`, so the word must
 * not survive anywhere a reader can see it - not as a label, not as a pill
 * colour, not as a list filter option.
 *
 * `isTerminalPriceTagStatus` is the other half and it is REQUEST-aware on
 * purpose: `approved` is the end of the line for a salesperson printing their
 * own tags and the middle of it for an office print.
 */
import { describe, it, expect } from 'vitest';

import {
  PRICE_TAG_STATUS_PILL_CLASS,
  priceTagStatusLabel,
  priceTagStatusPillClass,
} from './price-tag-status';
import {
  AUTO_COLLECT_DAYS_DEFAULT,
  AUTO_COLLECT_DAYS_MAX,
  AUTO_COLLECT_DAYS_MIN,
  autoCollectOn,
  isTerminalPriceTagStatus,
  printByLabel,
  PRINT_BY_OPTIONS,
} from './dealer-kit/print-collection';

describe('the label map (AC-S3-3)', () => {
  it('has no `ready` key at all', () => {
    expect(Object.keys(PRICE_TAG_STATUS_PILL_CLASS)).not.toContain('ready');
    // The generic fallback title-cases anything unknown, so the absence has to
    // be asserted on the map rather than on the rendered word.
    expect(priceTagStatusPillClass('ready')).toBe('bg-muted text-muted-foreground');
  });

  it('names the two collection statuses', () => {
    expect(priceTagStatusLabel('ready_for_collection')).toBe('Ready for collection');
    expect(priceTagStatusLabel('collected')).toBe('Collected');
    expect(priceTagStatusPillClass('ready_for_collection')).not.toBe(
      'bg-muted text-muted-foreground',
    );
    expect(priceTagStatusPillClass('collected')).not.toBe(
      'bg-muted text-muted-foreground',
    );
  });

  it('still names every status that survived', () => {
    expect(priceTagStatusLabel('proof_ready')).toBe('Design Ready');
    expect(priceTagStatusLabel('changes_requested')).toBe('Changes Requested');
    expect(priceTagStatusLabel('approved')).toBe('Approved');
    expect(priceTagStatusLabel('')).toBe('');
  });
});

describe('printByLabel (AC-S3-2)', () => {
  it('offers exactly the two choices, in the plan order', () => {
    expect(PRINT_BY_OPTIONS.map((option) => option.value)).toEqual(['office', 'self']);
    expect(printByLabel('office')).toBe('Office prints');
    expect(printByLabel('self')).toBe('I print myself');
  });

  it('a row from before the choice existed says so rather than guessing', () => {
    expect(printByLabel(null)).toBe('Not set');
    expect(printByLabel(undefined)).toBe('Not set');
  });
});

describe('isTerminalPriceTagStatus (AC-S3-4, AC-S3-6)', () => {
  it('approved is the end for a self print and the middle for an office print', () => {
    expect(isTerminalPriceTagStatus('approved', 'self')).toBe(true);
    expect(isTerminalPriceTagStatus('approved', 'office')).toBe(false);
    // No choice recorded: nothing has been decided, so nothing is finished.
    expect(isTerminalPriceTagStatus('approved', null)).toBe(false);
  });

  it('collected, rejected and void are finished whoever prints', () => {
    for (const printBy of ['office', 'self', null] as const) {
      expect(isTerminalPriceTagStatus('collected', printBy)).toBe(true);
      expect(isTerminalPriceTagStatus('rejected', printBy)).toBe(true);
      expect(isTerminalPriceTagStatus('void', printBy)).toBe(true);
    }
  });

  it('a hand-over still waiting is not finished', () => {
    expect(isTerminalPriceTagStatus('ready_for_collection', 'office')).toBe(false);
    expect(isTerminalPriceTagStatus('proof_ready', 'self')).toBe(false);
  });
});

describe('autoCollectOn (AC-S3-8 card subline)', () => {
  it('is the ready date plus the configured days', () => {
    const on = autoCollectOn('2026-09-01T00:00:00Z', 7);

    expect(on?.toISOString()).toBe('2026-09-08T00:00:00.000Z');
  });

  it('is nothing at all when the sweep is off', () => {
    expect(autoCollectOn('2026-09-01T00:00:00Z', 0)).toBeNull();
    expect(autoCollectOn('2026-09-01T00:00:00Z', null)).toBeNull();
    expect(autoCollectOn(null, 7)).toBeNull();
    expect(autoCollectOn('not a date', 7)).toBeNull();
  });

  it('carries the bounds the setting is validated against', () => {
    expect([AUTO_COLLECT_DAYS_MIN, AUTO_COLLECT_DAYS_MAX]).toEqual([0, 90]);
    expect(AUTO_COLLECT_DAYS_DEFAULT).toBe(7);
  });
});

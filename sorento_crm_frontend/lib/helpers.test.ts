/**
 * `parseDateTimeAsUTC` - the one seam every API timestamp and every API DATE reaches the
 * browser through (`formatDateInMalaysia` / `formatDateTimeInMalaysia` both parse with
 * it), so what it does with each shape on the wire is worth pinning.
 *
 * The date-only case is here because it SHIPPED BROKEN on one browser and not the other
 * (owner, on an iPhone, 16 Sep): the SO date column was blank in iOS Safari and correct
 * in Chrome. `'2025-09-10' + 'Z'` is not a string the ECMAScript date grammar defines -
 * V8 accepts it, JavaScriptCore does not - so Safari answered Invalid Date and every
 * formatter downstream answered an empty string. A parser difference reads exactly like
 * missing data, which is why the assertion below names the instant rather than the format.
 */
import { describe, expect, it } from 'vitest';
import { parseDateTimeAsUTC } from './helpers';

describe('parseDateTimeAsUTC', () => {
  it('reads a bare calendar day as midnight UTC, spelled the way every engine parses', () => {
    expect(parseDateTimeAsUTC('2025-09-10').toISOString()).toBe(
      '2025-09-10T00:00:00.000Z',
    );
  });

  it('keeps naive-UTC semantics for a datetime with no offset', () => {
    expect(parseDateTimeAsUTC('2025-09-10 14:30:00').toISOString()).toBe(
      '2025-09-10T14:30:00.000Z',
    );
    expect(parseDateTimeAsUTC('2025-09-10T14:30:00').toISOString()).toBe(
      '2025-09-10T14:30:00.000Z',
    );
  });

  it('leaves a string that already states its offset alone', () => {
    expect(parseDateTimeAsUTC('2025-09-10T14:30:00Z').toISOString()).toBe(
      '2025-09-10T14:30:00.000Z',
    );
    expect(parseDateTimeAsUTC('2025-09-10T22:30:00+08:00').toISOString()).toBe(
      '2025-09-10T14:30:00.000Z',
    );
  });

  it('answers an Invalid Date for an empty string rather than today', () => {
    expect(Number.isNaN(parseDateTimeAsUTC('').getTime())).toBe(true);
  });
});

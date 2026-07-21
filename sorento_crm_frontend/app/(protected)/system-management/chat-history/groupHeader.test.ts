/**
 * Group-header derivation for the chat-history listing. Covers UAC OBS-S5-21.
 *
 * The rule is pure and worth testing on its own: given a row and the one before
 * it, does this row open a new group? Extracted so the boundary logic is not
 * only reachable through a rendered grid.
 *
 * Contiguity is the API's job (`group_by` orders rows server-side). This only
 * decides where to draw the divider — if members were NOT contiguous, the same
 * group would render more than once, which is why grouping is not done purely
 * client-side over a paginated set.
 */
import { describe, it, expect } from 'vitest';
import { buildGroupHeader } from './groupHeader';

const row = (contact: string, iso: string) =>
  ({ contact_display: contact, sent_at: iso }) as never;

// 21/07 08:29 MYT is 20/07 00:29 UTC — the two disagree on the calendar day,
// which is exactly why the label is derived in Malaysia time.
const ANN_21ST = row('Ann (+60111)', '2026-07-21T00:29:00');
const ANN_21ST_LATER = row('Ann (+60111)', '2026-07-21T01:10:00');
const ANN_20TH = row('Ann (+60111)', '2026-07-20T01:00:00');
const BOB_21ST = row('Bob (+60222)', '2026-07-21T00:40:00');

describe('buildGroupHeader', () => {
  it('returns undefined when grouping is off, so the grid renders unchanged', () => {
    expect(buildGroupHeader('none')).toBeUndefined();
  });

  describe('by date', () => {
    const fn = buildGroupHeader('date')!;

    it('labels the first row', () => {
      expect(fn(ANN_21ST, null)).toBeTruthy();
    });

    it('does not repeat the label within the same day', () => {
      expect(fn(ANN_21ST_LATER, ANN_21ST)).toBeNull();
    });

    it('opens a new group when the day changes', () => {
      expect(fn(ANN_20TH, ANN_21ST)).toBeTruthy();
    });

    it('ignores a contact change within the same day', () => {
      expect(fn(BOB_21ST, ANN_21ST)).toBeNull();
    });
  });

  describe('by contact', () => {
    const fn = buildGroupHeader('contact')!;

    it('labels each new contact', () => {
      expect(fn(BOB_21ST, ANN_21ST)).toContain('Bob');
    });

    it('does not repeat within one contact, even across days', () => {
      expect(fn(ANN_20TH, ANN_21ST)).toBeNull();
    });
  });

  describe('by contact then date', () => {
    const fn = buildGroupHeader('contact_date')!;

    it('a new contact opens a combined contact + date header', () => {
      const label = fn(BOB_21ST, ANN_21ST) as string;
      expect(label).toContain('Bob');
      expect(label).toContain('21');
    });

    it('a new day inside one contact opens a date-only header', () => {
      const label = fn(ANN_20TH, ANN_21ST) as string;
      expect(label).not.toContain('Ann');
      expect(label).toContain('20');
    });

    it('is silent when neither contact nor day changed', () => {
      expect(fn(ANN_21ST_LATER, ANN_21ST)).toBeNull();
    });
  });
});

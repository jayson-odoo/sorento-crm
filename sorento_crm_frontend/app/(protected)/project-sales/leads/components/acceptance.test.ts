/**
 * P1 - the wait and the informant, in words.
 *
 * These are the two sentences the whole slice is judged on: "waiting 3 days" has to be
 * plain enough to act on, and an informant must never render as a buyer or as an id.
 */
import { describe, expect, it } from 'vitest';
import {
  acceptanceLabel,
  acceptanceBadgeVariant,
  describeWait,
  hoursSince,
  informantSourceLabel,
  informantSummary,
} from './acceptance';

describe('describeWait', () => {
  it('says under an hour rather than a fraction', () => {
    expect(describeWait(0)).toBe('Under an hour');
    expect(describeWait(0.4)).toBe('Under an hour');
  });

  it('rounds hours down and keeps the singular', () => {
    expect(describeWait(1)).toBe('1 hour');
    expect(describeWait(1.9)).toBe('1 hour');
    expect(describeWait(5.2)).toBe('5 hours');
  });

  it('switches to days at a day', () => {
    expect(describeWait(24)).toBe('1 day');
    expect(describeWait(47.5)).toBe('1 day');
    expect(describeWait(72)).toBe('3 days');
  });

  it('has nothing to say about a lead nobody assigned', () => {
    expect(describeWait(null)).toBeNull();
    expect(describeWait(undefined)).toBeNull();
    expect(describeWait(Number.NaN)).toBeNull();
  });
});

describe('hoursSince', () => {
  it('reads a naive backend timestamp as UTC', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3_600_000)
      .toISOString()
      .replace('Z', '');
    const hours = hoursSince(twoHoursAgo);
    expect(hours).not.toBeNull();
    expect(hours as number).toBeGreaterThan(1.9);
    expect(hours as number).toBeLessThan(2.1);
  });

  it('returns null when there is no timestamp', () => {
    expect(hoursSince(null)).toBeNull();
    expect(hoursSince('')).toBeNull();
  });
});

describe('informantSummary', () => {
  it('names the firm, the person and their reference, and never an id', () => {
    const summary = informantSummary({
      informant_source: 'bci',
      informant_party_id: '11111111-1111-1111-1111-111111111111',
      informant_party_label: 'Veritas Architects Sdn Bhd',
      informant_contact_name: 'Lim, QS',
      informant_ref: 'BCI-778812',
    });
    expect(summary).toBe('Veritas Architects Sdn Bhd, Lim, QS · BCI · BCI-778812');
    expect(summary).not.toContain('1111');
  });

  it('accepts a lone person with no firm on record', () => {
    expect(
      informantSummary({ informant_source: 'referral', informant_contact_name: 'Ali' }),
    ).toBe('Ali · Referral');
  });

  it('is null when nobody wrote anything down', () => {
    expect(informantSummary({})).toBeNull();
  });
});

describe('informantSourceLabel', () => {
  it('renders the code as a human label', () => {
    expect(informantSourceLabel('walk_in')).toBe('Walk in');
    expect(informantSourceLabel(null)).toBeNull();
  });
});

describe('acceptanceLabel', () => {
  it('reads as awaiting acceptance, not as assigned, because it is not owned yet', () => {
    expect(acceptanceLabel({ acceptance_state: 'assigned', owner_name: 'Ali' })).toBe(
      'Awaiting acceptance by Ali',
    );
  });

  it('names the owner once accepted', () => {
    expect(acceptanceLabel({ acceptance_state: 'accepted', owner_name: 'Ali' })).toBe(
      'Accepted by Ali',
    );
  });

  it('distinguishes never assigned from declined', () => {
    expect(acceptanceLabel({ acceptance_state: null, owner_name: null })).toBe(
      'Not assigned',
    );
    expect(acceptanceLabel({ acceptance_state: 'declined', owner_name: null })).toBe(
      'Declined',
    );
  });
});

describe('acceptanceBadgeVariant', () => {
  it('keeps an unaccepted lead visually unsettled', () => {
    expect(acceptanceBadgeVariant('assigned')).toBe('warning');
    expect(acceptanceBadgeVariant('accepted')).toBe('success');
    expect(acceptanceBadgeVariant('declined')).toBe('destructive');
    expect(acceptanceBadgeVariant(null)).toBe('outline');
  });
});

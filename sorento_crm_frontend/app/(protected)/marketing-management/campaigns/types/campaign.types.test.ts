import { describe, it, expect } from 'vitest';
import { CAMPAIGN_STATUSES, campaignStatusLabel } from './campaign.types';

describe('campaign status casing (Bug A5)', () => {
  it('exposes the 4 canonical LOWERCASE statuses (match DB constraint)', () => {
    expect(CAMPAIGN_STATUSES.map((s) => s.value)).toEqual([
      'planning',
      'active',
      'completed',
      'cancelled',
    ]);
  });

  it('title-cases a stored lowercase status', () => {
    expect(campaignStatusLabel('planning')).toBe('Planning');
    expect(campaignStatusLabel('active')).toBe('Active');
  });

  it('still resolves a stray uppercase value', () => {
    expect(campaignStatusLabel('PLANNING')).toBe('Planning');
  });

  it('returns a dash for empty/nullish', () => {
    expect(campaignStatusLabel(null)).toBe('-');
    expect(campaignStatusLabel('')).toBe('-');
  });

  it('passes through an unknown value unchanged', () => {
    expect(campaignStatusLabel('WHATEVER')).toBe('WHATEVER');
  });
});

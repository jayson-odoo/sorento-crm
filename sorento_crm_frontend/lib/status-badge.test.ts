/**
 * Phase 3 fix round 2, should-fix 3: the sales opportunity stage keys
 * (new/qualified/proposal/negotiation/won/lost, `sales_seed_service.py`'s
 * `DEFAULT_OPPORTUNITY_STATUSES`) resolve through the SAME shared `getStatusBadgeVariant`
 * every other status pill in the app uses, rather than a bespoke ternary per screen.
 */
import { describe, expect, it } from 'vitest';
import { getStatusBadgeVariant } from './status-badge';

describe('getStatusBadgeVariant - sales opportunity stages (fix2 should-fix 3)', () => {
  it('fix2 3: qualified is primary', () => {
    expect(getStatusBadgeVariant('qualified')).toBe('primary');
  });

  it('fix2 3: proposal is primary', () => {
    expect(getStatusBadgeVariant('proposal')).toBe('primary');
  });

  it('fix2 3: negotiation is warning', () => {
    expect(getStatusBadgeVariant('negotiation')).toBe('warning');
  });

  it('fix2 3: won is success', () => {
    expect(getStatusBadgeVariant('won')).toBe('success');
  });

  it('fix2 3: lost is destructive', () => {
    expect(getStatusBadgeVariant('lost')).toBe('destructive');
  });
});

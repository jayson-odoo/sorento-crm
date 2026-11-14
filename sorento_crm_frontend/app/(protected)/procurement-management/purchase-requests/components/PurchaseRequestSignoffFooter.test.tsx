/**
 * The shared sign-off (purchase request, sponsorship form, order change notice): the decision
 * Date is the Malaysia day of the UTC stamp, like every other date on the page (OCN round 9,
 * browser pass 2 D2). A decision at 04:07 in Malaysia is still the 12th in UTC.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PurchaseRequestSignoffFooter } from './PurchaseRequestSignoffFooter';

describe('PurchaseRequestSignoffFooter date', () => {
  it.each([
    ['a naive UTC stamp', '2026-11-12T20:07:45'],
    ['an offset stamp', '2026-11-12T20:07:45.387961+00:00'],
  ])('reads %s as the Malaysia day', (_label, stamp) => {
    render(
      <PurchaseRequestSignoffFooter
        variant="decision"
        request={{ approval_status: 'approved', approved_by: 'Manager A', approved_at: stamp, approval_comments: null }}
      />,
    );
    expect(screen.getByText('13/11/2026')).toBeTruthy();
    expect(screen.queryByText('12/11/2026')).toBeNull();
  });
});

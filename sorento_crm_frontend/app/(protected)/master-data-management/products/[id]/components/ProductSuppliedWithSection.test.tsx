/**
 * A real defect (supplied-with companions, review round 2, reproduced twice by hand):
 * Delete -> Cancel within the countdown left the "Delete rule" button `disabled` until
 * a page reload, even though the server kept the rule. `useDeferredRowAction`'s own
 * `targetId` never clears back to null after Cancel - by design, see
 * `hooks/useDeferredRowAction.test.tsx` - so a component reading `targetId === row.id`
 * ALONE for its disabled/spinner state stays stuck. The fix reads `targetId ===
 * row.id && isPending`, `ProductSuppliersSection.tsx`'s own pattern; this pins it.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

vi.mock('./AddCompanionRuleModal', () => ({
  AddCompanionRuleModal: () => null,
}));

const RULE = {
  id: 'rule-1',
  companion_product_id: 'companion-1',
  companion_item_code: 'CKSW015',
  companion_product_name: 'Seat cover',
  supplier_id: null,
  supplier_code: null,
  supplier_name: null,
  ratio: '1.0000',
  is_active: true,
  hosts: [{ product_id: 'host-1', item_code: 'CKS1050', product_name: 'Cistern' }],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const runMock = vi.fn();
let deletionValue: { run: typeof runMock; targetId: string | null; isPending: boolean };

vi.mock('../../hooks/useProductCompanions', () => ({
  useCompanionRulesForCompanion: () => ({ data: [RULE], isLoading: false, isError: false }),
  useCompanionRuleDelete: () => deletionValue,
}));

import { ProductSuppliedWithSection } from './ProductSuppliedWithSection';

describe('ProductSuppliedWithSection delete button', () => {
  it('re-enables once isPending goes back to false, not only when targetId clears', () => {
    deletionValue = { run: runMock, targetId: null, isPending: false };
    const { rerender } = render(<ProductSuppliedWithSection companionProductId="companion-1" />);

    const button = screen.getByRole('button', { name: /delete rule/i });
    expect(button).not.toBeDisabled();

    fireEvent.click(button);
    expect(runMock).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'rule-1' }),
    );

    // The countdown started: targetId names the row, isPending is true.
    deletionValue = { run: runMock, targetId: 'rule-1', isPending: true };
    rerender(<ProductSuppliedWithSection companionProductId="companion-1" />);
    expect(screen.getByRole('button', { name: /delete rule/i })).toBeDisabled();

    // Cancelled: the server kept the rule. `targetId` is NOT reset (by design), but
    // `isPending` is - the button must read that, not `targetId` alone.
    deletionValue = { run: runMock, targetId: 'rule-1', isPending: false };
    rerender(<ProductSuppliedWithSection companionProductId="companion-1" />);
    expect(screen.getByRole('button', { name: /delete rule/i })).not.toBeDisabled();
  });
});

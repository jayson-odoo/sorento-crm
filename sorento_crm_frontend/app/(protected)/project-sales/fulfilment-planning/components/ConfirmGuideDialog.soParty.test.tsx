/**
 * OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 19:35): the Confirm guide's page names its order's
 * customer and project under the SO number (the shared `CUSTOMER / project` line).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../_shared/services/lineSplitService', () => ({
  getLineSplits: vi.fn().mockResolvedValue(null),
  saveLineSplits: vi.fn(),
}));

import { ConfirmGuideDialog, type ConfirmGuidePage } from './ConfirmGuideDialog';

const page: ConfirmGuidePage = {
  psoId: null,
  salesOrderId: 'so-1',
  soNumber: 'SO000001',
  customerName: 'ACME SDN BHD (PROJECT)',
  projectLabel: 'TAMAN JAYA',
  covered: [
    {
      lineId: null, key: 'k-10', lineNo: 10, itemCode: 'ZZT-ITEM-1', location: 'BRW-BB', qty: 3,
      date: '2026-11-02', savedRemark: 'ORDER BACK', ownRemark: null, remarkEditable: true,
    },
  ],
};

describe('Confirm guide page header', () => {
  it('prints CUSTOMER / project under the SO number', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ConfirmGuideDialog
          pages={[page]}
          runConfirm={vi.fn().mockResolvedValue(true)}
          saveRemarks={vi.fn().mockResolvedValue(undefined)}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
    const section = screen.getByTestId('confirm-guide-split-page');
    expect(section.textContent).toContain('ACME SDN BHD (PROJECT) / TAMAN JAYA');
  });
});

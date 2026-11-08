/**
 * NPA-FROM-SI (owner 8 Nov 09:30): the stock inquiry form's customer field renders the shared
 * customer combobox (data-testid="customer-debtor-combobox"), the same one the NPA form renders.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));

import * as portalClient from '../lib/portal-client';
import { SubmissionClientProvider } from '../lib/submission-client';
import { SubmissionForm } from './SubmissionForm';
import { ME, SI_DETAIL } from './__fixtures__/crmSubmissionApi';

describe('stock inquiry customer field', () => {
  it('renders the shared customer combobox', async () => {
    const detail = SI_DETAIL({ id: 'si-9' });
    const client = {
      ...portalClient,
      fetchMe: vi.fn(async () => ({ ...ME })),
      fetchSubmission: vi.fn(async () => detail as never),
      fetchSubmissionNeighbours: vi.fn(async () => ({ prev_id: null, next_id: null, position: 1, total: 1 })),
      fetchRevisions: vi.fn(async () => []),
      fetchSubmissionComments: vi.fn(async () => []),
      lookupSet: vi.fn(async () => ({ options: [], defaultValue: null })),
      lookupProducts: vi.fn(async () => []),
      lookupDebtors: vi.fn(async () => []),
    };
    render(
      <SubmissionClientProvider client={client as never}>
        <SubmissionForm kind="stock_inquiry" submissionId="si-9" />
      </SubmissionClientProvider>,
    );
    expect(await screen.findAllByTestId('customer-debtor-combobox')).toHaveLength(1);
  });
});

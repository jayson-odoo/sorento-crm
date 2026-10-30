/**
 * PORTAL-P4-REQUESTS L3 pin (owner a25895124 Q2 a): the "Fulfilment DOs" tab is the CRM salesperson's
 * (the client gives the extra tab). The portal's own complaint form, with the portal client, has
 * Details / Comments / Revisions and no Fulfilment DOs tab.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));

import * as portalClient from '../lib/portal-client';
import { SubmissionClientProvider } from '../lib/submission-client';
import { SubmissionForm } from './SubmissionForm';
import { CMP_DETAIL, ME } from './__fixtures__/crmSubmissionApi';

describe('the portal complaint form', () => {
  it('shows Details / Comments / Revisions and no Fulfilment DOs tab', async () => {
    const client = {
      ...portalClient,
      fetchMe: vi.fn(async () => ({ ...ME })),
      fetchSubmission: vi.fn(async () => CMP_DETAIL({ status: 'submitted', is_draft: false, is_editable: false }) as never),
      fetchSubmissionNeighbours: vi.fn(async () => ({ prev_id: null, next_id: null, position: 1, total: 1 })),
      fetchRevisions: vi.fn(async () => []),
      fetchSubmissionComments: vi.fn(async () => []),
      lookupSet: vi.fn(async () => ({ options: [], defaultValue: null })),
      lookupProducts: vi.fn(async () => []),
      lookupDebtors: vi.fn(async () => []),
    };
    render(
      <SubmissionClientProvider client={client as never}>
        <SubmissionForm kind="complaint" submissionId="cp-5" />
      </SubmissionClientProvider>,
    );
    await screen.findByRole('tab', { name: /^Revisions/ });
    const names = screen.getAllByRole('tab').map((t) => (t.textContent ?? '').trim());
    expect(names.some((n) => /^Details/.test(n))).toBe(true);
    expect(names.some((n) => /^Comments/.test(n))).toBe(true);
    expect(names.some((n) => /Fulfilment/.test(n))).toBe(false);
  });
});

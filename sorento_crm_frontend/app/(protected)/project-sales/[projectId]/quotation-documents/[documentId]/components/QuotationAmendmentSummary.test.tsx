/**
 * QUOTE-CUSTOMER-AMEND fix round 1 (S3): a touched scope that already carries a hand-made draft
 * cannot be applied, and the summary row says so per scope with Apply off. Values invented.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { QuotationAmendmentRequest } from '../../../../_shared/types/project.types';
import { QuotationAmendmentSummary } from './QuotationAmendmentSummary';

function request(
  overrides: Partial<QuotationAmendmentRequest> = {},
): QuotationAmendmentRequest {
  return {
    id: 'req-1',
    status: 'open',
    submitted_at: '2026-10-30T06:05:00',
    requester_name: 'Buyer A',
    note: null,
    applied_at: null,
    rows: [
      {
        id: 'r1',
        line_id: 'l1',
        field: 'quantity',
        value_from: '120.00',
        value_to: '110.00',
        decision: 'accepted',
        decision_reason: null,
      },
    ],
    total_issued: '48000.00',
    total_after: '44000.00',
    blocked_scopes: [],
    revised: false,
    ...overrides,
  };
}

function renderSummary(value: QuotationAmendmentRequest) {
  return render(
    <QuotationAmendmentSummary
      request={value}
      canApply
      applying={false}
      onApply={vi.fn()}
      suggestedOnly
      onSuggestedOnly={vi.fn()}
    />,
  );
}

describe('QuotationAmendmentSummary with a hand-made draft on a touched scope', () => {
  it('names each blocked scope and turns Apply off; a clean request can apply', () => {
    const { unmount } = renderSummary(
      request({
        blocked_scopes: [
          {
            quotation_id: 'q1',
            scope_label: 'Block A',
            version_id: 'v1',
            has_accepted: true,
          },
        ],
      }),
    );
    expect(
      screen.getByText(
        'A revision is already open on Block A, so accepted suggestions cannot be applied to it. Issuing that revision closes these suggestions.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Apply decisions' }),
    ).toBeDisabled();
    unmount();

    renderSummary(request());
    expect(screen.queryByText(/A revision is already open/)).toBeNull();
    expect(
      screen.getByRole('button', { name: 'Apply decisions' }),
    ).toBeEnabled();
  });
});

describe('QuotationAmendmentSummary blocked before any decision (D2)', () => {
  it('says why at once, with nothing decided, and Apply is off', () => {
    renderSummary(
      request({
        rows: request().rows.map((row) => ({
          ...row,
          decision: 'pending' as const,
        })),
        blocked_scopes: [
          {
            quotation_id: 'q1',
            scope_label: 'Block A',
            version_id: 'v1',
            has_accepted: false,
          },
        ],
      }),
    );
    expect(
      screen.getByText(
        'A revision is already open on Block A, so accepted suggestions cannot be applied to it. Issuing that revision closes these suggestions.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Apply decisions' }),
    ).toBeDisabled();
    // The suggestions stay decidable on the issued version, so the decide-the-rest hint stands.
    expect(screen.getByText(/Accept or reject/)).toBeInTheDocument();
  });
});

describe('QuotationAmendmentSummary matches the server on a blocked scope (S3b)', () => {
  const blockedScope = (hasAccepted: boolean) => [
    {
      quotation_id: 'q1',
      scope_label: 'Block A',
      version_id: 'v1',
      has_accepted: hasAccepted,
    },
  ];

  it('keeps Apply on when the blocked scope holds only rejected rows', () => {
    renderSummary(
      request({
        rows: request().rows.map((row) => ({
          ...row,
          decision: 'rejected' as const,
        })),
        blocked_scopes: blockedScope(false),
      }),
    );
    // The warning stays for every touched scope with a draft.
    expect(
      screen.getByText(/A revision is already open on Block A/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Apply decisions' }),
    ).toBeEnabled();
  });

  it('turns Apply off when an accepted row sits on the blocked scope, and names it', () => {
    renderSummary(request({ blocked_scopes: blockedScope(true) }));
    expect(
      screen.getByRole('button', { name: 'Apply decisions' }),
    ).toBeDisabled();
    expect(
      screen.getByText('Accepted suggestions on Block A cannot be applied.'),
    ).toBeInTheDocument();
  });
});

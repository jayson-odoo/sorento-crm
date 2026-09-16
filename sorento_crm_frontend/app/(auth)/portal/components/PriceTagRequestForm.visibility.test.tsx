/**
 * PLAN-portal-forms-market-segment D7 r3: a `/new` page makes no request of
 * its own to check visibility - it reuses the same `/me` fetch as every
 * other portal form and renders the same inline blocked message the edit
 * page's real 403 uses (AC-L4). The server remains the enforcement; this
 * only avoids an empty form.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../lib/price-tag-request-service', () => ({
  lookupDebtors: vi.fn(async () => []),
  lookupPromotions: vi.fn(async () => []),
  lookupTagItems: vi.fn(async () => []),
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  updateRequest: vi.fn(),
  deleteRequest: vi.fn(),
  submitRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
  listReviewComments: vi.fn(async () => []),
  collectRequest: vi.fn(),
}));

const fetchMe = vi.fn();
vi.mock('../lib/portal-client', () => ({
  uploadAttachment: vi.fn(),
  getPriceTagDesign: vi.fn(),
  fetchMe: (...a: unknown[]) => fetchMe(...a),
}));

// Native `<select>` stand-in - same shape as the sibling suites.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={props.id === 'debtor' ? 'Customer' : (props.placeholder ?? '')}
      value={props.value}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('./AttachmentDropzone', () => ({ AttachmentDropzone: () => null }));

import { PriceTagRequestForm } from './PriceTagRequestForm';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PriceTagRequestForm - a /new page reads visible_form_types off the already-fetched /me (D7 r3)', () => {
  it('blocks the form when the contact does not hold the price tag grant', async () => {
    fetchMe.mockResolvedValue({ visible_form_types: ['stock_inquiry'] });
    render(<PriceTagRequestForm />);

    expect(
      await screen.findByText('Price Tag Request is not available for your account.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back to your forms' })).toBeInTheDocument();
    // No empty form underneath the message.
    expect(screen.queryByLabelText('Customer')).toBeNull();
  });

  it('renders the form as usual once the grant is present', async () => {
    fetchMe.mockResolvedValue({ visible_form_types: ['price_tag_request'] });
    render(<PriceTagRequestForm />);

    await screen.findByLabelText('Customer');
    expect(
      screen.queryByText('is not available for your account.', { exact: false }),
    ).toBeNull();
  });

  it('makes no extra request beyond the existing /me fetch (no new guard fetch, D7)', async () => {
    fetchMe.mockResolvedValue({ visible_form_types: ['stock_inquiry'] });
    render(<PriceTagRequestForm />);

    await screen.findByText('Price Tag Request is not available for your account.');
    expect(fetchMe).toHaveBeenCalledTimes(1);
  });
});

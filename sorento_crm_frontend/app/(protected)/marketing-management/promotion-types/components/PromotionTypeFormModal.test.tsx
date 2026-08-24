/**
 * PromotionTypeFormModal - create/edit of a promotion type.
 *
 * The payload assertions matter more than the layout: `show_expired` off has to
 * clear both bounds, or a type that is never served after expiry still carries a
 * stale "until end of year" the next admin would read as live configuration.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const createPromotionType = vi.fn();
const updatePromotionType = vi.fn();
vi.mock('../services/promotionTypeService', () => ({
  createPromotionType: (...a: unknown[]) => createPromotionType(...a),
  updatePromotionType: (...a: unknown[]) => updatePromotionType(...a),
  getPromotionTypes: vi.fn(),
  getPromotionType: vi.fn(),
  deletePromotionType: vi.fn(),
}));

import PromotionTypeFormModal from './PromotionTypeFormModal';

const EXISTING = {
  id: 'type-pp',
  type_code: 'pp',
  type_name: 'PP Promo',
  description: 'PP offer',
  show_expired: true,
  expired_valid_until_year_end: true,
  expired_max_age_days: null,
  match_markers: ['pp'],
  match_priority: 20,
  is_default: false,
  sort_order: 20,
  promotions_count: 4,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
};

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  createPromotionType.mockResolvedValue({ ...EXISTING });
  updatePromotionType.mockResolvedValue({ ...EXISTING });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('PromotionTypeFormModal', () => {
  it('requires a code and a name', async () => {
    render(<PromotionTypeFormModal open onOpenChange={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: /create/i }));

    expect(await screen.findByText('Code is required')).toBeInTheDocument();
    expect(screen.getByText('Name is required')).toBeInTheDocument();
    expect(createPromotionType).not.toHaveBeenCalled();
  });

  it('creates with lowercase, comma-split markers', async () => {
    render(<PromotionTypeFormModal open onOpenChange={() => {}} />);

    fireEvent.change(screen.getByPlaceholderText('special'), { target: { value: 'Clearance' } });
    fireEvent.change(screen.getByPlaceholderText('Special Promo'), {
      target: { value: 'Clearance Promo' },
    });
    fireEvent.change(screen.getByPlaceholderText('special, clearance'), {
      target: { value: 'Clearance, END OF LINE' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => expect(createPromotionType).toHaveBeenCalled());
    expect(createPromotionType).toHaveBeenCalledWith(
      expect.objectContaining({
        type_code: 'Clearance',
        type_name: 'Clearance Promo',
        match_markers: ['clearance', 'end of line'],
        show_expired: false,
        // Bounds are meaningless while the type is never served after expiry.
        expired_valid_until_year_end: false,
        expired_max_age_days: null,
      }),
    );
  });

  it('hides the bounds until the type is served after expiry', async () => {
    render(<PromotionTypeFormModal open onOpenChange={() => {}} />);

    expect(screen.queryByText('Until end of year')).not.toBeInTheDocument();

    // First switch is "Show when expired"; the bounds only exist under it.
    fireEvent.click(screen.getAllByRole('switch')[0]);

    expect(await screen.findByText('Until end of year')).toBeInTheDocument();
    expect(screen.getByText('Max age (days)')).toBeInTheDocument();
  });

  it('edits an existing type through the update path', async () => {
    render(<PromotionTypeFormModal open onOpenChange={() => {}} promotionType={EXISTING} />);

    expect(await screen.findByDisplayValue('PP Promo')).toBeInTheDocument();
    // 'pp' is both the code and its marker, so query the field, not the value.
    expect(screen.getByPlaceholderText('special')).toHaveValue('pp');
    expect(screen.getByPlaceholderText('special, clearance')).toHaveValue('pp');

    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(updatePromotionType).toHaveBeenCalled());
    expect(updatePromotionType).toHaveBeenCalledWith(
      'type-pp',
      expect.objectContaining({
        type_code: 'pp',
        show_expired: true,
        expired_valid_until_year_end: true,
      }),
    );
  });
});

/**
 * Which promotion prices this brochure (S7.2, PLAN D5).
 *
 * The assertions that matter here are the ones a redesign quietly loses: a
 * promotion is shown by its name and never by its id, a promotion with no
 * description still reads as words, "no promotion" says what the reader gets
 * rather than looking like an unfinished field, and a save that failed does not
 * leave the control looking as though it worked (the S7.0 defect, in a new
 * place).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../../services/dealerKitService', () => ({
  setPagePromotion: vi.fn(),
}));

vi.mock('../../../services/brochureImageService', () => ({
  PROMOTION_PAGE_SIZE: 50,
  listBrochureImagePromotionOptions: vi.fn(),
}));

import { toast } from '@/lib/toast';

import { listBrochureImagePromotionOptions } from '../../../services/brochureImageService';
import { setPagePromotion } from '../../../services/dealerKitService';
import { PagePromotionControl } from './PagePromotionControl';

const mockSet = vi.mocked(setPagePromotion);
const mockPromotions = vi.mocked(listBrochureImagePromotionOptions);

const FLYER = { value: 'promo-a3', label: '_SORENTO A3 FLYER 2025-2026_compressed' };
const DEALER = { value: 'promo-dealer', label: 'KITCHEN SINK PROMO DEALER.pdf' };

function renderControl(props: Partial<React.ComponentProps<typeof PagePromotionControl>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PagePromotionControl
        pageId="page-1"
        promotionId={null}
        promotionLabel={null}
        {...props}
      />
    </QueryClientProvider>,
  );
}

const trigger = () =>
  document.querySelector('[data-slot="searchable-select-trigger"]') as HTMLElement;

beforeEach(() => {
  vi.clearAllMocks();
  mockPromotions.mockResolvedValue([FLYER, DEALER]);
  mockSet.mockResolvedValue({ promotionId: null, promotionLabel: null });
  // Radix uses pointer capture on open; jsdom does not implement it.
  Element.prototype.scrollIntoView = vi.fn();
  (Element.prototype as unknown as Record<string, unknown>).hasPointerCapture = vi.fn();
  (Element.prototype as unknown as Record<string, unknown>).setPointerCapture = vi.fn();
  (Element.prototype as unknown as Record<string, unknown>).releasePointerCapture = vi.fn();
});

describe('PagePromotionControl', () => {
  it('shows the linked promotion by name, never by id', () => {
    renderControl({ promotionId: FLYER.value, promotionLabel: FLYER.label });

    expect(trigger()).toHaveTextContent(FLYER.label);
    expect(document.body.textContent).not.toContain(FLYER.value);
  });

  it('reads a promotion with no description as words rather than an id', () => {
    renderControl({ promotionId: 'promo-nameless', promotionLabel: null });

    expect(trigger()).toHaveTextContent('Untitled promotion');
    expect(document.body.textContent).not.toContain('promo-nameless');
  });

  it('says what an unlinked brochure costs the reader', () => {
    renderControl();

    // Not a blank field: a page with no promotion is finished, and what it
    // shows is the list price.
    expect(trigger()).toHaveTextContent(/list prices/i);
  });

  it('saves the promotion a user picks', async () => {
    mockSet.mockResolvedValue({ promotionId: FLYER.value, promotionLabel: FLYER.label });
    renderControl();

    fireEvent.click(trigger());
    fireEvent.click(await screen.findByRole('option', { name: new RegExp(FLYER.label) }));

    await waitFor(() => expect(mockSet).toHaveBeenCalledWith('page-1', FLYER.value));
    await waitFor(() => expect(trigger()).toHaveTextContent(FLYER.label));
    expect(toast.success).toHaveBeenCalled();
  });

  it('searches the server rather than filtering one cached page', async () => {
    // There are hundreds of promotions: a static list would silently cap at
    // whatever the first page happened to hold.
    renderControl();
    fireEvent.click(trigger());

    await waitFor(() => expect(mockPromotions).toHaveBeenCalled());
    expect(mockPromotions).toHaveBeenCalledWith('', 0);
  });

  it('clears the link back to list prices', async () => {
    renderControl({ promotionId: FLYER.value, promotionLabel: FLYER.label });

    fireEvent.pointerDown(screen.getByLabelText('Clear selection'));

    await waitFor(() => expect(mockSet).toHaveBeenCalledWith('page-1', null));
    await waitFor(() => expect(trigger()).toHaveTextContent(/list prices/i));
  });

  it('keeps showing the saved promotion when the save fails', async () => {
    mockSet.mockRejectedValue(new Error('Promotion not found'));
    renderControl({ promotionId: DEALER.value, promotionLabel: DEALER.label });

    fireEvent.click(trigger());
    fireEvent.click(await screen.findByRole('option', { name: new RegExp(FLYER.label) }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Promotion not found'));
    // The S7.0 lesson: a control that looks changed after a failed save sends
    // somebody away believing a decision was recorded.
    expect(trigger()).toHaveTextContent(DEALER.label);
  });
});

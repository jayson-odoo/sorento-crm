/**
 * The brochure image picker, against the real service (S7.0 phase 2).
 *
 * These assertions are the ones a rewire silently drops. A product with one
 * candidate is the obvious place to "help" by auto-choosing, a product with no
 * candidate is the obvious row to filter out, and a filename is the obvious
 * thing to hide for a tidier grid - each of which puts the wrong photograph in
 * front of a customer, or hides the fact that no photograph exists at all.
 */
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../services/brochureImageService', () => ({
  BROCHURE_IMAGE_PAGE_SIZE: 25,
  PROMOTION_PAGE_SIZE: 50,
  listBrochureImages: vi.fn(),
  setBrochureImage: vi.fn(),
  clearBrochureImage: vi.fn(),
  listBrochureImagePromotionOptions: vi.fn(),
}));

import {
  clearBrochureImage,
  listBrochureImages,
  listBrochureImagePromotionOptions,
  setBrochureImage,
} from '../../services/brochureImageService';
import type {
  BrochureImageCandidate,
  BrochureImagePage,
  BrochureImageRow,
} from '../../services/brochureImageService';
import { BrochureImagePicker } from './BrochureImagePicker';

const mockList = vi.mocked(listBrochureImages);
const mockSet = vi.mocked(setBrochureImage);
const mockPromotions = vi.mocked(listBrochureImagePromotionOptions);

function candidate(
  index: number,
  filename: string,
  accessLevels: string[] | null = null,
): BrochureImageCandidate {
  return { attachmentId: `att-${index}`, filename, url: null, accessLevels };
}

/**
 * Modelled on the live data: SRTWC286-SH really does have a blank page and two
 * other products' photographs among its linked images.
 */
const MESSY_ROW: BrochureImageRow = {
  productId: 'p-1',
  productCode: 'SRTWC286-SH',
  productName: 'One Piece Water Closet, S-Trap',
  chosenAttachmentId: null,
  candidates: [
    candidate(1, 'SRTWC286-SH.jpg'),
    candidate(2, '61. BLANK PAGE_PG12.jpg'),
    candidate(3, 'SRTBF3141-GY_01.jpg'),
  ],
};

const SINGLE_CANDIDATE_ROW: BrochureImageRow = {
  productId: 'p-2',
  productCode: 'SRTSCBD320',
  productName: 'Bidet Seat Cover',
  chosenAttachmentId: null,
  candidates: [candidate(30, 'SRTSCBD320.jpg')],
};

const NO_CANDIDATE_ROW: BrochureImageRow = {
  productId: 'p-3',
  productCode: 'SRT2210-2',
  productName: 'Towel Ring',
  chosenAttachmentId: null,
  candidates: [],
};

const CHOSEN_ROW: BrochureImageRow = {
  productId: 'p-4',
  productCode: 'SRTWC8354-SH',
  productName: 'One Piece Water Closet, Twister Flushing',
  chosenAttachmentId: 'att-20',
  candidates: [candidate(20, 'SRTWC8354-SH.jpg'), candidate(21, 'SRTWC8354-SH_02.jpg')],
};

function page(items: BrochureImageRow[]): BrochureImagePage {
  return {
    items,
    total: items.length,
    remaining: items.filter((row) => !row.chosenAttachmentId).length,
    shown: items.length,
  };
}

function renderPicker() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={client}>
      <BrochureImagePicker />
    </QueryClientProvider>,
  );
  return { ...utils, client };
}

/** The candidate tile for a filename, whatever wrapper it renders inside. */
function tile(filename: string): HTMLElement {
  const found = document.querySelector(`[data-dk-bi-candidate="${filename}"]`);
  expect(found).not.toBeNull();
  return found as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockPromotions.mockResolvedValue([]);
});

describe('BrochureImagePicker', () => {
  it('shows placeholders while the products are loading', () => {
    mockList.mockReturnValue(new Promise<BrochureImagePage>(() => {}));

    const { container } = renderPicker();

    expect(container.querySelector('[data-dk-bi-loading]')).not.toBeNull();
  });

  it('says the list could not be loaded when the request fails', async () => {
    mockList.mockRejectedValue(new Error('Could not load brochure images'));

    const { container } = renderPicker();

    // The query retries once before giving up, so the error state is a second
    // away rather than immediate.
    await waitFor(() => expect(container.querySelector('[data-dk-bi-error]')).not.toBeNull(), {
      timeout: 4000,
    });
    expect(screen.getByText(/could not load brochure images/i)).toBeInTheDocument();
  });

  it('reports an empty result rather than rendering nothing', async () => {
    mockList.mockResolvedValue(page([]));

    const { container } = renderPicker();

    await waitFor(() => expect(container.querySelector('[data-dk-bi-empty]')).not.toBeNull());
  });

  it('renders a row per product with every candidate filename shown', async () => {
    mockList.mockResolvedValue(page([MESSY_ROW]));

    renderPicker();

    expect(await screen.findByText('SRTWC286-SH')).toBeInTheDocument();
    // The filename is the only thing telling a blank page apart from the
    // product, so it is never hidden behind a hover or a tooltip alone.
    expect(screen.getByText('SRTWC286-SH.jpg')).toBeInTheDocument();
    expect(screen.getByText('61. BLANK PAGE_PG12.jpg')).toBeInTheDocument();
    expect(screen.getByText('SRTBF3141-GY_01.jpg')).toBeInTheDocument();
  });

  it('leaves a single-candidate product unchosen until it is clicked', async () => {
    mockList.mockResolvedValue(page([SINGLE_CANDIDATE_ROW]));

    renderPicker();

    await screen.findByText('SRTSCBD320');
    expect(tile('SRTSCBD320.jpg')).toHaveAttribute('aria-pressed', 'false');
    // Nothing is chosen on the user's behalf, however obvious the answer looks.
    expect(mockSet).not.toHaveBeenCalled();
  });

  it('keeps a product with no candidates in the list and says a photo is needed', async () => {
    mockList.mockResolvedValue(page([NO_CANDIDATE_ROW]));

    renderPicker();

    expect(await screen.findByText('SRT2210-2')).toBeInTheDocument();
    expect(screen.getByText(/no photo is linked to this product yet/i)).toBeInTheDocument();
  });

  it('marks the candidate that is already chosen', async () => {
    mockList.mockResolvedValue(page([CHOSEN_ROW]));

    renderPicker();

    await screen.findByText('SRTWC8354-SH');
    expect(tile('SRTWC8354-SH.jpg')).toHaveAttribute('aria-pressed', 'true');
    expect(tile('SRTWC8354-SH_02.jpg')).toHaveAttribute('aria-pressed', 'false');
  });

  it('sends the product and the attachment when a candidate is clicked', async () => {
    mockList.mockResolvedValue(page([MESSY_ROW]));
    mockSet.mockResolvedValue({ productId: 'p-1', chosenAttachmentId: 'att-3' });

    renderPicker();
    await screen.findByText('SRTWC286-SH');

    await act(async () => {
      fireEvent.click(tile('SRTBF3141-GY_01.jpg'));
    });

    await waitFor(() => expect(mockSet).toHaveBeenCalledWith('p-1', 'att-3'));
  });

  it('leaves the choice in place when the chosen candidate is clicked again', async () => {
    mockList.mockResolvedValue(page([CHOSEN_ROW]));

    renderPicker();
    await screen.findByText('SRTWC8354-SH');

    await act(async () => {
      fireEvent.click(tile('SRTWC8354-SH.jpg'));
    });

    // Idempotent, never a toggle: a second click must not leave the product
    // with no image, which would silently put the tile back on row order.
    expect(tile('SRTWC8354-SH.jpg')).toHaveAttribute('aria-pressed', 'true');
    expect(tile('SRTWC8354-SH_02.jpg')).toHaveAttribute('aria-pressed', 'false');
    expect(vi.mocked(clearBrochureImage)).not.toHaveBeenCalled();
  });

  it('shows the clicked candidate as chosen before the list refetches', async () => {
    mockList.mockResolvedValue(page([SINGLE_CANDIDATE_ROW]));
    mockSet.mockResolvedValue({ productId: 'p-2', chosenAttachmentId: 'att-30' });

    renderPicker();
    await screen.findByText('SRTSCBD320');

    await act(async () => {
      fireEvent.click(tile('SRTSCBD320.jpg'));
    });

    await waitFor(() =>
      expect(tile('SRTSCBD320.jpg')).toHaveAttribute('aria-pressed', 'true'),
    );
  });

  it('asks the server for only the products still without an image by default', async () => {
    mockList.mockResolvedValue(page([]));

    renderPicker();

    await waitFor(() => expect(mockList).toHaveBeenCalled());
    expect(mockList.mock.calls[0][0]).toMatchObject({ onlyUnset: true });
  });
});

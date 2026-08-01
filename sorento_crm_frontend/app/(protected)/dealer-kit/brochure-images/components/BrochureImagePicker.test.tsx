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
  listBrochureImagePromotionOptions: vi.fn(),
}));

// Setting the flag is product master data; this screen is the second caller of
// the one service, not a second copy of it.
vi.mock(
  '@/app/(protected)/master-data-management/products/services/productBrochureImageService',
  () => ({
    setBrochureImage: vi.fn(),
    clearBrochureImage: vi.fn(),
  }),
);

import { toast } from 'sonner';
import {
  clearBrochureImage,
  setBrochureImage,
} from '@/app/(protected)/master-data-management/products/services/productBrochureImageService';
import {
  listBrochureImages,
  listBrochureImagePromotionOptions,
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
const mockToastError = vi.mocked(toast.error);

/** A promise this test resolves or rejects on cue, to hold a save in flight. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  // Attached now because an unhandled rejection between the reject() and the
  // mutation's own catch fails the run on its own.
  promise.catch(() => {});
  return { promise, resolve, reject };
}

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

  it('tells the user what to do next instead of how the system works', async () => {
    mockList.mockResolvedValue(page([]));

    const { container } = renderPicker();

    await waitFor(() => expect(container.querySelector('[data-dk-bi-empty]')).not.toBeNull());
    // The next step, yes; what the choice is wired into downstream, no.
    expect(screen.getByText(/turn off the filter/i)).toBeInTheDocument();
    expect(screen.queryByText(/3D model/i)).toBeNull();
    expect(screen.queryByText(/catalogue tile/i)).toBeNull();
  });

  it('tells the user what to do about a product with no photo', async () => {
    mockList.mockResolvedValue(page([NO_CANDIDATE_ROW, MESSY_ROW]));

    renderPicker();

    await screen.findByText('SRT2210-2');
    expect(screen.queryByText(/photo shoot/i)).toBeNull();
    expect(screen.getByText(/attach a photo/i)).toBeInTheDocument();
  });

  it('says the no-photo count is the page it counted, not the whole filter', async () => {
    // The banner can only count the rows it has. Across the filter the real
    // figure is 465, so an unqualified "1 product has no photo" on page 1 is a
    // number somebody would plan a photo shoot around.
    mockList.mockResolvedValue({
      items: [NO_CANDIDATE_ROW, MESSY_ROW],
      total: 998,
      remaining: 465,
      shown: 465,
    });

    renderPicker();

    await screen.findByText('SRT2210-2');
    expect(screen.getByText(/1 product on this page has no photo/i)).toBeInTheDocument();
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

  it('keeps an answered product where it is, though the server would drop it', async () => {
    // What the server really does with only_unset on: the answered product is
    // gone from the next page. Letting that reach the list slides every row
    // below it up by a card mid-click-sequence, so the next click lands on a
    // product the user was not looking at - the exact way a wrong photo ends up
    // in front of a customer.
    mockList.mockResolvedValueOnce(page([SINGLE_CANDIDATE_ROW, MESSY_ROW]));
    mockList.mockResolvedValue(page([MESSY_ROW]));
    mockSet.mockResolvedValue({ productId: 'p-2', chosenAttachmentId: 'att-30' });

    const { container } = renderPicker();
    await screen.findByText('SRTSCBD320');

    await act(async () => {
      fireEvent.click(tile('SRTSCBD320.jpg'));
    });

    await waitFor(() => expect(mockSet).toHaveBeenCalledWith('p-2', 'att-30'));
    // Long enough for a refetch to land, if one were ever fired.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(tile('SRTSCBD320.jpg')).toHaveAttribute('aria-pressed', 'true');
    expect(
      Array.from(container.querySelectorAll('[data-dk-bi-row]')).map((row) =>
        row.getAttribute('data-dk-bi-row'),
      ),
    ).toEqual(['SRTSCBD320', 'SRTWC286-SH']);
  });

  it('counts down what is left as each product is answered', async () => {
    mockList.mockResolvedValue({
      items: [SINGLE_CANDIDATE_ROW],
      total: 998,
      remaining: 98,
      shown: 98,
    });
    mockSet.mockResolvedValue({ productId: 'p-2', chosenAttachmentId: 'att-30' });

    const { container } = renderPicker();
    await screen.findByText('SRTSCBD320');

    await act(async () => {
      fireEvent.click(tile('SRTSCBD320.jpg'));
    });

    // Holding the row still must not also freeze the number beside it, or the
    // header reads the same after an hour of work.
    await waitFor(() =>
      expect(
        container.querySelector('[data-dk-bi-remaining]')?.textContent?.replace(/\s+/g, ' '),
      ).toBe('97 of 998 still to choose'),
    );
  });

  it('takes the mark back off when the save fails, and leaves the count alone', async () => {
    // The mark is the only record of the decision. A save that 404s (product
    // outside the company scope), 400s (not an image) or 500s while the tile
    // still reads "chosen" tells the user this product is answered when it is
    // not, and nobody finds out until a customer is looking at the wrong photo.
    mockList.mockResolvedValue({
      items: [SINGLE_CANDIDATE_ROW],
      total: 998,
      remaining: 98,
      shown: 98,
    });
    mockSet.mockRejectedValue(new Error('Attachment is not linked to this product'));

    const { container } = renderPicker();
    await screen.findByText('SRTSCBD320');

    await act(async () => {
      fireEvent.click(tile('SRTSCBD320.jpg'));
    });

    await waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith('Attachment is not linked to this product'),
    );
    expect(tile('SRTSCBD320.jpg')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByText('chosen')).toBeNull();
    // The count and the list have to agree: a product still in the backlog that
    // stopped being counted is one the worklist can never be finished on.
    expect(
      container.querySelector('[data-dk-bi-remaining]')?.textContent?.replace(/\s+/g, ' '),
    ).toBe('98 of 998 still to choose');
  });

  it('puts the previous choice back when a re-choice fails', async () => {
    // Rolling back to "nothing chosen" would be its own lie: this product was
    // answered, and the failed attempt to change the answer did not unanswer it.
    mockList.mockResolvedValue(page([CHOSEN_ROW]));
    mockSet.mockRejectedValue(new Error('Product not found'));

    renderPicker();
    await screen.findByText('SRTWC8354-SH');

    await act(async () => {
      fireEvent.click(tile('SRTWC8354-SH_02.jpg'));
    });

    await waitFor(() => expect(mockToastError).toHaveBeenCalledWith('Product not found'));
    expect(tile('SRTWC8354-SH.jpg')).toHaveAttribute('aria-pressed', 'true');
    expect(tile('SRTWC8354-SH_02.jpg')).toHaveAttribute('aria-pressed', 'false');
  });

  it('leaves a later choice marked when an earlier save on the same product fails', async () => {
    // Two clicks in a row on one product, and the abandoned first save answers
    // last. Rolling back on the product rather than on the attempt would clear a
    // mark the user is entitled to keep.
    const first = deferred<{ productId: string; chosenAttachmentId: string }>();
    const second = deferred<{ productId: string; chosenAttachmentId: string }>();
    mockList.mockResolvedValue(page([MESSY_ROW]));
    mockSet.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    renderPicker();
    await screen.findByText('SRTWC286-SH');

    await act(async () => {
      fireEvent.click(tile('61. BLANK PAGE_PG12.jpg'));
    });
    await act(async () => {
      fireEvent.click(tile('SRTWC286-SH.jpg'));
    });

    await act(async () => {
      first.reject(new Error('Attachment is not linked to this product'));
      await Promise.resolve();
    });

    expect(tile('SRTWC286-SH.jpg')).toHaveAttribute('aria-pressed', 'true');
    expect(tile('61. BLANK PAGE_PG12.jpg')).toHaveAttribute('aria-pressed', 'false');

    await act(async () => {
      second.resolve({ productId: 'p-1', chosenAttachmentId: 'att-1' });
    });
    expect(tile('SRTWC286-SH.jpg')).toHaveAttribute('aria-pressed', 'true');
  });

  it('offers only the pages it can actually list', async () => {
    // The A3 flyer promotion: 998 products, 900 of them already answered. The
    // server reports total 998 but can only list the 98 still unanswered, so a
    // pager built on `total` invites 36 clicks onto pages that hold nothing.
    const rows = Array.from({ length: 25 }, (_, index) => ({
      ...SINGLE_CANDIDATE_ROW,
      productId: `p-${index}`,
      productCode: `SRT-${index}`,
      candidates: [candidate(100 + index, `SRT-${index}.jpg`)],
    }));
    mockList.mockResolvedValue({ items: rows, total: 998, remaining: 98, shown: 98 });

    const { container } = renderPicker();

    await screen.findByText('SRT-0');
    expect(container.querySelector('[data-dk-bi-pager] span')?.textContent).toBe('Page 1 of 4');
  });

  it('asks the server for only the products still without an image by default', async () => {
    mockList.mockResolvedValue(page([]));

    renderPicker();

    await waitFor(() => expect(mockList).toHaveBeenCalled());
    expect(mockList.mock.calls[0][0]).toMatchObject({ onlyUnset: true });
  });
});

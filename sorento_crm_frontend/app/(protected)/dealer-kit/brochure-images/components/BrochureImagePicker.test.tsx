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
  adoptSingleBrochureImages: vi.fn(),
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
  adoptSingleBrochureImages,
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
const mockAdopt = vi.mocked(adoptSingleBrochureImages);

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
    choosable: items.filter((row) => row.candidates.length > 0).length,
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

/**
 * Open a product's photo dialog.
 *
 * The candidates are no longer laid out under every row: with 11,390 products
 * that buried the codes people navigate by. They open per row instead.
 */
async function openRow(productCode: string) {
  const button = document.querySelector(`[data-dk-bi-open="${productCode}"]`);
  expect(button).not.toBeNull();
  await act(async () => {
    fireEvent.click(button as HTMLElement);
  });
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
  // Answers nothing unless a test says otherwise, so a fixture with a single
  // candidate stays unanswered and the tests about CHOOSING still test choosing.
  mockAdopt.mockResolvedValue([]);
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
      choosable: 533,
    });

    renderPicker();

    await screen.findByText('SRT2210-2');
    expect(screen.getByText(/1 product on this page has no photo/i)).toBeInTheDocument();
  });

  it('renders a row per product with every candidate filename shown', async () => {
    mockList.mockResolvedValue(page([MESSY_ROW]));

    renderPicker();

    expect(await screen.findByText('SRTWC286-SH')).toBeInTheDocument();
    await openRow('SRTWC286-SH');
    // The filename is the only thing telling a blank page apart from the
    // product, so it is never hidden behind a hover or a tooltip alone.
    expect(screen.getByText('SRTWC286-SH.jpg')).toBeInTheDocument();
    expect(screen.getByText('61. BLANK PAGE_PG12.jpg')).toBeInTheDocument();
    expect(screen.getByText('SRTBF3141-GY_01.jpg')).toBeInTheDocument();
  });

  it('takes the only photo a product has, without asking', async () => {
    /*
      This REVERSES the rule these tests used to pin, and the reversal is only
      correct for one reason. Nothing is GUESSED on the user's behalf - a
      filename that looks like the product code is still never trusted. But with
      exactly ONE candidate there is no choice to get wrong: the renderer
      already falls back to the first linked photo, so recording it changes
      nothing a reader sees. 509 of the flyer's 535 products are in that state,
      and asking somebody to press OK five hundred times is a toll, not a
      decision.
    */
    mockList.mockResolvedValue(page([SINGLE_CANDIDATE_ROW]));
    mockAdopt.mockResolvedValue(['p-2']);

    renderPicker();

    await screen.findByText('SRTSCBD320');
    await waitFor(() => expect(mockAdopt).toHaveBeenCalledWith(['p-2']));
    // And it says so, rather than looking like a product somebody reviewed.
    expect(await screen.findByText(/only photo/i)).toBeInTheDocument();
  });

  it('does not answer a product that has a real choice to make', async () => {
    mockList.mockResolvedValue(page([MESSY_ROW]));

    renderPicker();

    await screen.findByText('SRTWC286-SH');
    // Three candidates, one of them a blank page and one another product
    // entirely. Somebody has to look.
    await waitFor(() => expect(mockAdopt).not.toHaveBeenCalled());
  });

  it('does not answer a product that has no photo at all', async () => {
    // Paired with a product that HAS photos: a page where nothing is choosable
    // is a different screen entirely (its own empty state), and this test is
    // about the row, not that state.
    mockList.mockResolvedValue(page([NO_CANDIDATE_ROW, MESSY_ROW]));

    renderPicker();

    await screen.findByText('SRT2210-2');
    // The answer there is a photo shoot, not a click.
    await waitFor(() => expect(mockAdopt).not.toHaveBeenCalled());
  });

  it('keeps a product with no candidates in the list and says a photo is needed', async () => {
    // Alongside a product that HAS one, which is the real shape of this
    // catalogue: 465 of the flyer's codes have no photo and 533 do. A page whose
    // only row has no candidate is a different situation entirely - there is
    // nothing to choose between at all - and it has its own empty state below.
    mockList.mockResolvedValue(page([NO_CANDIDATE_ROW, SINGLE_CANDIDATE_ROW]));

    renderPicker();

    expect(await screen.findByText('SRT2210-2')).toBeInTheDocument();
    // Said on the row itself, where somebody scanning the list will see it.
    // The longer sentence lives in the dialog, which this product cannot open.
    expect(screen.getAllByText(/no photo/i).length).toBeGreaterThan(0);
    expect(
      document.querySelector('[data-dk-bi-open="SRT2210-2"]'),
    ).toBeDisabled();
  });

  it('marks the candidate that is already chosen', async () => {
    mockList.mockResolvedValue(page([CHOSEN_ROW]));

    renderPicker();

    await screen.findByText('SRTWC8354-SH');
    await openRow('SRTWC8354-SH');
    expect(tile('SRTWC8354-SH.jpg')).toHaveAttribute('aria-pressed', 'true');
    expect(tile('SRTWC8354-SH_02.jpg')).toHaveAttribute('aria-pressed', 'false');
  });

  it('sends the product and the attachment when a candidate is clicked', async () => {
    mockList.mockResolvedValue(page([MESSY_ROW]));
    mockSet.mockResolvedValue({ productId: 'p-1', chosenAttachmentId: 'att-3' });

    renderPicker();
    await screen.findByText('SRTWC286-SH');
    await openRow('SRTWC286-SH');
    await openRow('SRTWC286-SH');

    await act(async () => {
      fireEvent.click(tile('SRTBF3141-GY_01.jpg'));
    });

    await waitFor(() => expect(mockSet).toHaveBeenCalledWith('p-1', 'att-3'));
  });

  it('leaves the choice in place when the chosen candidate is clicked again', async () => {
    mockList.mockResolvedValue(page([CHOSEN_ROW]));

    renderPicker();
    await screen.findByText('SRTWC8354-SH');
    await openRow('SRTWC8354-SH');
    await openRow('SRTWC8354-SH');

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
    await openRow('SRTSCBD320');

    await act(async () => {
      fireEvent.click(tile('SRTSCBD320.jpg'));
    });

    await waitFor(() => expect(mockSet).toHaveBeenCalledWith('p-2', 'att-30'));
    // Long enough for a refetch to land, if one were ever fired.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    // The dialog has moved on to the next product by now - choosing is a
    // sitting and each choice advances - so the mark is checked by coming back
    // to the row rather than by whatever happens to be on screen.
    await openRow('SRTSCBD320');
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
      choosable: 533,
    });
    mockSet.mockResolvedValue({ productId: 'p-2', chosenAttachmentId: 'att-30' });

    const { container } = renderPicker();
    await screen.findByText('SRTSCBD320');
    await openRow('SRTSCBD320');
    await openRow('SRTSCBD320');

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
      choosable: 533,
    });
    mockSet.mockRejectedValue(new Error('Attachment is not linked to this product'));

    const { container } = renderPicker();
    await screen.findByText('SRTSCBD320');
    await openRow('SRTSCBD320');

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
    await openRow('SRTWC8354-SH');

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
    await openRow('SRTWC286-SH');

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
    mockList.mockResolvedValue({ items: rows, total: 998, remaining: 98, shown: 98, choosable: 533 });

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

describe('BrochureImagePicker, a company with no product photos at all', () => {
  /**
   * The default landing state for such a company, and it used to read
   * "11390 of 11390 still to choose" over a full page of products with nothing
   * under any of them. Every word of that is true and the whole screen reads as
   * broken, because "no photos anywhere" and "none on THIS page" are
   * indistinguishable until you have paged through 1,139 of them.
   *
   * `choosable` is the filter-wide count that tells them apart, so these
   * assertions are about which of the two answers the screen gives.
   */
  const NOTHING_ANYWHERE: BrochureImagePage = {
    items: [NO_CANDIDATE_ROW],
    total: 11390,
    remaining: 11390,
    shown: 11390,
    choosable: 0,
  };

  it('says there is nothing to choose from, not that there is work to do', async () => {
    mockList.mockResolvedValue(NOTHING_ANYWHERE);

    const { container } = renderPicker();

    await waitFor(() =>
      expect(container.querySelector('[data-dk-bi-no-photos]')).not.toBeNull(),
    );
    expect(screen.getByText(/no product here has a photo yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/11390 of 11390 still to choose/i)).toBeNull();
  });

  it('counts the products rather than promising choices that cannot be made', async () => {
    mockList.mockResolvedValue(NOTHING_ANYWHERE);

    renderPicker();

    await screen.findByText(/none with a photo yet/i);
    expect(screen.getByText('11390 products, none with a photo yet')).toBeInTheDocument();
  });

  it('sends them where photos are attached', async () => {
    mockList.mockResolvedValue(NOTHING_ANYWHERE);

    renderPicker();

    const link = await screen.findByRole('link', { name: /go to files/i });
    expect(link).toHaveAttribute('href', '/resource-management/attachment-directories');
  });

  it('does not also render rows, the page banner or a pager behind it', async () => {
    // 456 pages of products with no photos is a lot of nothing to page through,
    // and the page-scoped "1 product on this page has no photo" restates what
    // the empty state just said about all 11,390 as if it were a local problem.
    mockList.mockResolvedValue(NOTHING_ANYWHERE);

    const { container } = renderPicker();

    await waitFor(() =>
      expect(container.querySelector('[data-dk-bi-no-photos]')).not.toBeNull(),
    );
    expect(container.querySelector('[data-dk-bi-row="SRT2210-2"]')).toBeNull();
    expect(container.querySelector('[data-dk-bi-pager]')).toBeNull();
    expect(screen.queryByText(/on this page has no photo/i)).toBeNull();
  });

  it('is NOT shown to a catalogue that merely has none on this page', async () => {
    // The boundary the whole field exists for. Same visible rows, same zero
    // candidates among them - but the filter holds 533 products with photos, so
    // this is an ordinary page and the ordinary banner is the right answer.
    mockList.mockResolvedValue({
      items: [NO_CANDIDATE_ROW],
      total: 998,
      remaining: 465,
      shown: 465,
      choosable: 533,
    });

    const { container } = renderPicker();

    await screen.findByText('SRT2210-2');
    expect(container.querySelector('[data-dk-bi-no-photos]')).toBeNull();
    expect(screen.getByText(/465 of 998 still to choose/i)).toBeInTheDocument();
    expect(screen.getByText(/1 product on this page has no photo/i)).toBeInTheDocument();
  });

  it('is NOT shown for a finished catalogue, which is a different empty state', async () => {
    // Everything answered: no rows left under the filter, but the photos are
    // all there. Reporting "no photos anywhere" would be exactly backwards.
    mockList.mockResolvedValue({
      items: [],
      total: 998,
      remaining: 0,
      shown: 0,
      choosable: 998,
    });

    const { container } = renderPicker();

    await waitFor(() => expect(container.querySelector('[data-dk-bi-empty]')).not.toBeNull());
    expect(container.querySelector('[data-dk-bi-no-photos]')).toBeNull();
  });

  it('walks to the next product without closing', async () => {
    // Choosing photos is a sitting, not an errand. Closing to open the next row
    // costs two clicks per product and loses the user's place.
    mockList.mockResolvedValue(page([MESSY_ROW, CHOSEN_ROW]));

    renderPicker();
    await screen.findByText('SRTWC286-SH');
    await openRow('SRTWC286-SH');

    expect(screen.getByText('61. BLANK PAGE_PG12.jpg')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /next/i }));
    });

    expect(screen.getByText('SRTWC8354-SH_02.jpg')).toBeInTheDocument();
    expect(screen.queryByText('61. BLANK PAGE_PG12.jpg')).toBeNull();
  });

  it('walks back to the previous product', async () => {
    mockList.mockResolvedValue(page([MESSY_ROW, CHOSEN_ROW]));

    renderPicker();
    await screen.findByText('SRTWC8354-SH');
    await openRow('SRTWC8354-SH');

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /previous/i }));
    });

    expect(screen.getByText('61. BLANK PAGE_PG12.jpg')).toBeInTheDocument();
  });

  it('stops at both ends rather than wrapping round', async () => {
    // Arriving back at the first product after the last reads as the list
    // having reloaded, and the user starts again.
    mockList.mockResolvedValue(page([MESSY_ROW, CHOSEN_ROW]));

    renderPicker();
    await screen.findByText('SRTWC286-SH');
    await openRow('SRTWC286-SH');

    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /next/i }));
    });

    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
  });

  it('moves on by itself once a photo is chosen', async () => {
    mockList.mockResolvedValue(page([MESSY_ROW, CHOSEN_ROW]));
    mockSet.mockResolvedValue({ productId: 'p-1', chosenAttachmentId: 'att-1' });

    renderPicker();
    await screen.findByText('SRTWC286-SH');
    await openRow('SRTWC286-SH');

    await act(async () => {
      fireEvent.click(tile('SRTWC286-SH.jpg'));
    });

    // The next product, not a closed dialog: the whole point is that this is
    // one sitting.
    expect(await screen.findByText('SRTWC8354-SH_02.jpg')).toBeInTheDocument();
  });

  it('stays put on the last product so a final choice can be corrected', async () => {
    mockList.mockResolvedValue(page([CHOSEN_ROW]));
    mockSet.mockResolvedValue({ productId: 'p-4', chosenAttachmentId: 'att-21' });

    renderPicker();
    await screen.findByText('SRTWC8354-SH');
    await openRow('SRTWC8354-SH');

    await act(async () => {
      fireEvent.click(tile('SRTWC8354-SH_02.jpg'));
    });

    expect(tile('SRTWC8354-SH_02.jpg')).toHaveAttribute('aria-pressed', 'true');
  });
});

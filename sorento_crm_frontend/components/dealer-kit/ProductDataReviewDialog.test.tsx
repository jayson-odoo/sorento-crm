/**
 * The product-data review dialog (r9 S5/D18, AC-S5-4).
 *
 * The question the dialog asks is "is this new value the one you want
 * printed", and it cannot be answered without seeing both, so every changed
 * field renders old AND new. Neither answer is styled as the safe one: a price
 * that moved after the salesperson approved the proof is often exactly the
 * thing NOT to print, so `Keep current` is as legitimate as `Update tag`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import ProductDataReviewDialog from './ProductDataReviewDialog';
import type { LineDataChangeSet } from '@/lib/dealer-kit/product-data-changes';

/**
 * THE REAL WIRE SHAPE. `LineDataChangeSet` is answered by
 * `GET .../data-changes`, whose response model declares `old_image_url` and
 * `new_image_url`, so FastAPI serialises them as `null` on every row - text
 * rows included. A fixture that omits the keys tests a body the server never
 * sends: `undefined` and `null` take different branches, and only one of them
 * is what a reader actually gets.
 */
const CHANGE_SET: LineDataChangeSet = {
  line_id: 'line-1',
  code: 'ZZT-SINK-1',
  name: 'ZZT Kitchen Sink',
  changes: [
    {
      field: 'list_price',
      label: 'List price',
      old: 'RM 1,000',
      new: 'RM 1,200',
      old_image_url: null,
      new_image_url: null,
      note: null,
    },
    {
      field: 'barcode',
      label: 'Barcode',
      old: '9550000000001',
      new: '9550000000999',
      old_image_url: null,
      new_image_url: null,
      note: null,
    },
    {
      field: 'offer_price',
      label: 'Offer price',
      old: 'RM 899',
      new: null,
      old_image_url: null,
      new_image_url: null,
      note: 'Promotion ended',
    },
    {
      field: 'image:att-1',
      label: 'Photo',
      old: 'old.jpg',
      new: 'new.jpg',
      old_image_url: 'https://cdn.example.test/old.jpg',
      new_image_url: 'https://cdn.example.test/new.jpg',
      note: null,
    },
  ],
};

function renderDialog(overrides: Partial<React.ComponentProps<typeof ProductDataReviewDialog>> = {}) {
  const onDecide = vi.fn(async () => {});
  const onOpenChange = vi.fn();
  const result = render(
    <ProductDataReviewDialog
      open
      onOpenChange={onOpenChange}
      changeSet={CHANGE_SET}
      onDecide={onDecide}
      {...overrides}
    />,
  );
  return { ...result, onDecide, onOpenChange };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('what the dialog shows (AC-S5-4)', () => {
  it('names the line by its code, never by its id', () => {
    renderDialog();

    expect(screen.getByText(/ZZT-SINK-1/)).toBeInTheDocument();
    expect(screen.queryByText('line-1')).toBeNull();
  });

  it('renders one row per changed field with both values', () => {
    renderDialog();
    const rows = screen.getByTestId('product-data-review-rows');

    expect(within(rows).getByText('List price')).toBeInTheDocument();
    expect(within(rows).getByText('RM 1,000')).toBeInTheDocument();
    expect(within(rows).getByText('RM 1,200')).toBeInTheDocument();
    expect(within(rows).getByText('9550000000001')).toBeInTheDocument();
    expect(within(rows).getByText('9550000000999')).toBeInTheDocument();
  });

  it('a text row with a null image url still shows its values, not "No photo"', () => {
    // The whole defect: `imageUrl !== undefined` is true for `null`, so every
    // text row takes the image branch and the reader is asked to choose
    // between "No photo" and "No photo".
    renderDialog();
    const rows = screen.getByTestId('product-data-review-rows');

    expect(within(rows).queryByText('No photo')).toBeNull();
    expect(within(rows).getByText('RM 1,000')).toBeInTheDocument();
    expect(within(rows).getByText('RM 1,200')).toBeInTheDocument();
  });

  it('only an image row renders a thumbnail', () => {
    renderDialog();

    // Four changed fields, one of them an image: two thumbnails, not eight.
    expect(screen.getAllByRole('img')).toHaveLength(2);
  });

  it('an offer that disappeared shows the old value and says why', () => {
    renderDialog();
    const rows = screen.getByTestId('product-data-review-rows');

    expect(within(rows).getByText('RM 899')).toBeInTheDocument();
    expect(within(rows).getByText('Promotion ended')).toBeInTheDocument();
  });

  it('draws thumbnails for an image change rather than a filename', () => {
    renderDialog();

    // The dialog renders through a portal, so the images are on the body, not
    // in the render container.
    const sources = screen
      .getAllByRole('img')
      .map((node) => node.getAttribute('src'));
    expect(sources).toContain('https://cdn.example.test/old.jpg');
    expect(sources).toContain('https://cdn.example.test/new.jpg');
  });

  it('says why the offer disappeared instead of showing a bare blank', () => {
    renderDialog();

    expect(screen.getByText('Promotion ended')).toBeInTheDocument();
  });

  it('draws nothing at all when there is no line under review', () => {
    const { container } = renderDialog({ changeSet: null });

    expect(container).toBeEmptyDOMElement();
  });
});

describe('the two answers (AC-S5-4)', () => {
  it('Keep current reports keep and closes', async () => {
    const { onDecide, onOpenChange } = renderDialog();

    fireEvent.click(screen.getByRole('button', { name: /Keep current/ }));

    await waitFor(() => expect(onDecide).toHaveBeenCalledWith('keep'));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('Update tag reports update and closes', async () => {
    const { onDecide, onOpenChange } = renderDialog();

    fireEvent.click(screen.getByRole('button', { name: /Update tag/ }));

    await waitFor(() => expect(onDecide).toHaveBeenCalledWith('update'));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('a failed decision leaves the dialog open with the question still on it', async () => {
    const onDecide = vi.fn(async () => {
      throw new Error('Network is down');
    });
    const onOpenChange = vi.fn();
    render(
      <ProductDataReviewDialog
        open
        onOpenChange={onOpenChange}
        changeSet={CHANGE_SET}
        onDecide={onDecide}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Update tag/ }));

    await waitFor(() => expect(onDecide).toHaveBeenCalled());
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(screen.getByText('List price')).toBeInTheDocument();
  });

  it('neither button can be pressed twice while the first is running', async () => {
    let release: () => void = () => {};
    const onDecide = vi.fn(
      () => new Promise<void>((resolve) => {
        release = resolve;
      }),
    );
    render(
      <ProductDataReviewDialog
        open
        onOpenChange={vi.fn()}
        changeSet={CHANGE_SET}
        onDecide={onDecide}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Update tag/ }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Keep current/ })).toBeDisabled(),
    );
    release();
  });
});

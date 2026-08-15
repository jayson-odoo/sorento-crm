/**
 * Choosing products out of seventeen thousand.
 *
 * The complaint this answers is that it was not intuitive, and the diagnosis is
 * that choosing a bath is a LOOKING task built as a reading task: rows of code
 * and name, no pictures, no grouping, and a chosen list that was one truncated
 * line of codes you could not take anything back out of.
 *
 * So the assertions here are mostly about what a person can SEE and UNDO, not
 * about the set arithmetic underneath (which `collection_membership` already
 * pins on the server).
 */
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/productPickerService', () => ({
  PICKER_PAGE_SIZE: 50,
  listPickerProducts: vi.fn(),
  listPickerCategories: vi.fn(),
  listProductThumbnails: vi.fn(),
}));

// The rule half is the shared RuleBuilder against the shared fact source, and
// it fetches its own field list. Not what this file is about.
vi.mock('@/components/rule-builder/RuleBuilder', () => ({
  RuleBuilder: () => <div data-testid="rule-builder" />,
}));

import {
  listPickerCategories,
  listPickerProducts,
  listProductThumbnails,
  type PickerProduct,
} from '../services/productPickerService';
import { EMPTY_SELECTION, ProductPickerDialog } from './ProductPickerDialog';

const mockProducts = vi.mocked(listPickerProducts);
const mockCategories = vi.mocked(listPickerCategories);
const mockThumbnails = vi.mocked(listProductThumbnails);

function product(overrides: Partial<PickerProduct> & { id: string }): PickerProduct {
  return {
    code: `SRT${overrides.id}`,
    name: `Product ${overrides.id}`,
    category: 'Bathtubs',
    brand: 'Sorento',
    price: 'MYR 100.00',
    isDiscontinued: false,
    ...overrides,
  };
}

const BATH = product({ id: '1', code: 'SRTBT1855', name: 'Freestanding Bath', category: 'Bathtubs' });
const BASIN = product({ id: '2', code: 'SRTWB3401', name: 'Wall Basin', category: 'Basins' });
const TAP = product({ id: '3', code: 'SRTTP0900', name: 'Pillar Tap', category: 'Basins' });

function renderPicker(onSave = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={client}>
      <ProductPickerDialog
        open
        onOpenChange={vi.fn()}
        value={EMPTY_SELECTION}
        onSave={onSave}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onSave };
}

/**
 * Switch to the hand-picking tab, which is what every test here is about.
 *
 * `mouseDown`, not `click`: a Radix tab activates on pointer-DOWN, so a bare
 * click leaves the trigger `data-state="inactive"` and the panel never mounts.
 */
async function openByHand() {
  await act(async () => {
    fireEvent.mouseDown(screen.getByRole('tab', { name: /by hand/i }));
  });
}

function card(code: string): HTMLElement {
  const found = document.querySelector(`[data-dk-picker-card="${code}"]`);
  expect(found).not.toBeNull();
  return found as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockCategories.mockResolvedValue([]);
  mockThumbnails.mockResolvedValue({});
  mockProducts.mockResolvedValue([BATH, BASIN, TAP]);
});

describe('ProductPickerDialog', () => {
  it('shows each product as a card, not a line of text', async () => {
    renderPicker();
    await openByHand();

    await waitFor(() => expect(card('SRTBT1855')).toBeInTheDocument());
    expect(card('SRTWB3401')).toBeInTheDocument();
  });

  it('shows the photograph when there is one', async () => {
    // SRTBF11404 and SRTBF11608 are indistinguishable as text and obvious as
    // pictures. That is the whole argument for the card.
    mockThumbnails.mockResolvedValue({ '1': 'https://cdn.example/bath.jpg' });

    renderPicker();
    await openByHand();

    await waitFor(() =>
      expect(card('SRTBT1855').querySelector('img')).toHaveAttribute(
        'src',
        'https://cdn.example/bath.jpg',
      ),
    );
  });

  it('falls back to a no-image state rather than a broken picture', async () => {
    renderPicker();
    await openByHand();

    await waitFor(() => expect(card('SRTWB3401')).toBeInTheDocument());
    expect(card('SRTWB3401').querySelector('img')).toBeNull();
  });

  it('groups results by product category', async () => {
    renderPicker();
    await openByHand();

    await waitFor(() =>
      expect(document.querySelector('[data-dk-picker-group="Bathtubs"]')).not.toBeNull(),
    );
    expect(document.querySelector('[data-dk-picker-group="Basins"]')).not.toBeNull();
    // Counted, so a group says how much is behind it.
    expect(screen.getByText('(2)')).toBeInTheDocument();
  });

  it('folds a category away and back', async () => {
    renderPicker();
    await openByHand();

    await waitFor(() => expect(card('SRTWB3401')).toBeInTheDocument());

    const header = screen.getByRole('button', { name: /Basins/ });
    await act(async () => {
      fireEvent.click(header);
    });
    expect(document.querySelector('[data-dk-picker-card="SRTWB3401"]')).toBeNull();
    // The bath is in a different group and must not have gone with it.
    expect(card('SRTBT1855')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(header);
    });
    expect(card('SRTWB3401')).toBeInTheDocument();
  });

  it('starts with every category open', async () => {
    // A picker that starts folded hides everything the user came for.
    renderPicker();
    await openByHand();

    await waitFor(() => expect(card('SRTBT1855')).toBeInTheDocument());
    expect(card('SRTWB3401')).toBeInTheDocument();
  });

  it('lists what has been chosen, beside the results', async () => {
    renderPicker();
    await openByHand();

    await waitFor(() => expect(card('SRTBT1855')).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(card('SRTBT1855'));
    });

    expect(document.querySelector('[data-dk-chosen="SRTBT1855"]')).not.toBeNull();
    expect(screen.getByText('1 chosen')).toBeInTheDocument();
  });

  it('takes a product back out from the chosen list', async () => {
    // The point of the pane. Before this, undoing a choice meant finding the
    // product again among 22,000.
    renderPicker();
    await openByHand();

    await waitFor(() => expect(card('SRTBT1855')).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(card('SRTBT1855'));
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Remove SRTBT1855' }));
    });

    expect(document.querySelector('[data-dk-chosen="SRTBT1855"]')).toBeNull();
    expect(screen.getByText('0 chosen')).toBeInTheDocument();
  });

  it('keeps naming a chosen product after the user searches for something else', async () => {
    /*
      The bug that makes a basket useless: the chosen list emptying itself as
      you browse. The list is the USER'S, so it has to survive the results
      underneath it changing.
    */
    renderPicker();
    await openByHand();

    await waitFor(() => expect(card('SRTBT1855')).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(card('SRTBT1855'));
    });

    // A search that returns something else entirely.
    mockProducts.mockResolvedValue([BASIN]);
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/search products/i), {
        target: { value: 'basin' },
      });
    });
    await waitFor(() => expect(document.querySelector('[data-dk-picker-card="SRTBT1855"]')).toBeNull());

    expect(document.querySelector('[data-dk-chosen="SRTBT1855"]')).not.toBeNull();
    expect(screen.getByText('1 chosen')).toBeInTheDocument();
  });

  it('says so when nothing is chosen yet', async () => {
    renderPicker();
    await openByHand();

    await waitFor(() => expect(card('SRTBT1855')).toBeInTheDocument());
    expect(screen.getByText(/nothing chosen yet/i)).toBeInTheDocument();
  });

  it('hands the chosen products back on save', async () => {
    const onSave = vi.fn();
    renderPicker(onSave);
    await openByHand();

    await waitFor(() => expect(card('SRTWB3401')).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(card('SRTWB3401'));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /use these products/i }));
    });

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ pinnedProductIds: ['2'] }),
    );
  });

  it('asks the server for the photos of the products it is showing, and no more', async () => {
    // Signing is not free. The picker must never ask for the catalogue's photos.
    renderPicker();
    await openByHand();

    await waitFor(() => expect(mockThumbnails).toHaveBeenCalled());
    expect(mockThumbnails).toHaveBeenCalledWith(['1', '2', '3']);
  });
});

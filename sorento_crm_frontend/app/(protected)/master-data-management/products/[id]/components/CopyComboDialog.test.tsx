/**
 * COMBO-COPY-TO-PRODUCTS: "Copy to other products" on each combo and its picker / confirm dialog.
 * Plan: documentation/plans/products/PLAN-combo-copy-to-products-09nov.md (owner answers 9 Nov).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const service = vi.hoisted(() => ({ copyProductCombo: vi.fn() }));
const products = vi.hoisted(() => ({ getProducts: vi.fn() }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock('../../services/productComboService', () => service);
vi.mock('../../services/productService', () => products);
vi.mock('@/lib/toast', () => ({ toast }));
vi.mock('../../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [], error: null, refetch: vi.fn() }),
}));
vi.mock('../../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [], error: null, refetch: vi.fn() }),
}));

import { CopyComboDialog, comboCopySummaryLines } from './CopyComboDialog';
import { comboCopyResultLine } from '../../hooks/useProductCombos';
import type { ComboCopySummary } from '../../services/productComboService';

const SOURCE = 'p-source';
const COMBO = 'combo-1';

const row = (id: string, code: string, extra: Record<string, unknown> = {}) => ({
  id,
  product_code: code,
  product_name: `ZZT ${code}`,
  is_active: true,
  ...extra,
});
const PAGE = [
  row(SOURCE, 'ZZT-BT1860'),
  row('p1', 'ZZT-BT1835'),
  row('p2', 'ZZT-BT1846', { is_discontinued: true }),
  row('p3', 'ZZT-BT1859'),
];

const target = (id: string, code: string) => ({ product_id: id, code, name: `ZZT ${code}` });

function summary(extra: Partial<ComboCopySummary> = {}): ComboCopySummary {
  return {
    targets: 3,
    created: 1,
    overwritten: 0,
    skipped: [
      { ...target('p2', 'ZZT-BT1846'), reason: 'exists' },
      { ...target('p3', 'ZZT-BT1859'), reason: 'exists' },
    ],
    conflicts: [target('p2', 'ZZT-BT1846'), target('p3', 'ZZT-BT1859')],
    template_links_copied: true,
    ...extra,
  };
}

function mount(onOpenChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CopyComboDialog
        open
        onOpenChange={onOpenChange}
        sourceProductId={SOURCE}
        comboId={COMBO}
        comboName="Bathtub Combo"
      />
    </QueryClientProvider>,
  );
  return onOpenChange;
}

async function pickAllAndNext() {
  for (const code of ['ZZT-BT1835', 'ZZT-BT1846', 'ZZT-BT1859']) {
    fireEvent.click(await screen.findByRole('checkbox', { name: `Select ${code}` }));
  }
  expect(screen.getByText('3 products picked')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Next' }));
  return screen.findByTestId('copy-combo-summary');
}

beforeEach(() => {
  vi.clearAllMocks();
  products.getProducts.mockResolvedValue({ data: PAGE, pagination: { total: 4, page: 1, limit: 25 } });
  service.copyProductCombo.mockResolvedValue(summary());
});

describe('CopyComboDialog picker', () => {
  it('names the combo, offers active products and cannot tick the source', async () => {
    mount();
    expect(screen.getByRole('dialog').textContent).toContain('Copy combo "Bathtub Combo" to other products');
    const box = await screen.findByRole('checkbox', { name: 'Select ZZT-BT1860' });
    expect(box.hasAttribute('disabled') || box.getAttribute('data-disabled') !== null).toBe(true);
    expect(products.getProducts).toHaveBeenCalledWith(expect.objectContaining({ status: 'active' }));
  });

  it('keeps a discontinued product pickable with a grey hint', async () => {
    mount();
    const box = await screen.findByRole('checkbox', { name: 'Select ZZT-BT1846' });
    expect(box.hasAttribute('disabled')).toBe(false);
    expect(screen.getByText('Discontinued').className).toContain('text-muted-foreground');
  });

  it('keeps the title clear of the close X at 375px', () => {
    mount();
    expect(screen.getByRole('heading', { name: /Copy combo/ }).className).toContain('pe-8');
  });
});

describe('CopyComboDialog confirm step', () => {
  it('previews with a dry run and lists each same-named combo with Skip chosen', async () => {
    mount();
    const panel = await pickAllAndNext();
    expect(service.copyProductCombo).toHaveBeenCalledWith(COMBO, ['p1', 'p2', 'p3'], [], true);
    expect(within(panel).getByText('Copy combo "Bathtub Combo" to 3 products.')).toBeTruthy();
    expect(within(panel).getByText('1 product gets it as a new combo.')).toBeTruthy();
    const conflicts = screen.getByTestId('copy-combo-conflicts');
    expect(conflicts.textContent).toContain('2 products already have a combo called "Bathtub Combo".');
    for (const code of ['ZZT-BT1846', 'ZZT-BT1859']) {
      const group = within(conflicts).getByRole('group', { name: `${code}: skip or overwrite` });
      expect(within(group).getByRole('radio', { name: 'Skip' }).getAttribute('aria-checked')).toBe('true');
    }
  });

  it('states the 500 cap', async () => {
    mount();
    await pickAllAndNext();
    expect(screen.getByTestId('copy-cap-note').textContent).toBe('One copy takes at most 500 products.');
  });

  it('by default copies with nothing overwritten', async () => {
    const onOpenChange = mount();
    await pickAllAndNext();
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
    await waitFor(() => expect(service.copyProductCombo).toHaveBeenLastCalledWith(COMBO, ['p1', 'p2', 'p3'], []));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(toast.success).toHaveBeenCalled();
  });

  it('sends only the products chosen to overwrite', async () => {
    mount();
    await pickAllAndNext();
    const group = screen.getByRole('group', { name: 'ZZT-BT1859: skip or overwrite' });
    fireEvent.click(within(group).getByRole('radio', { name: 'Overwrite' }));
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
    await waitFor(() =>
      expect(service.copyProductCombo).toHaveBeenLastCalledWith(COMBO, ['p1', 'p2', 'p3'], ['p3']),
    );
  });

  it('"Overwrite all" chooses every conflict, and turning it off skips them again', async () => {
    mount();
    await pickAllAndNext();
    const all = screen.getByRole('switch', { name: 'Overwrite all' });
    fireEvent.click(all);
    for (const code of ['ZZT-BT1846', 'ZZT-BT1859']) {
      const group = screen.getByRole('group', { name: `${code}: skip or overwrite` });
      expect(within(group).getByRole('radio', { name: 'Overwrite' }).getAttribute('aria-checked')).toBe('true');
    }
    // One row back to Skip turns the switch off.
    const first = screen.getByRole('group', { name: 'ZZT-BT1846: skip or overwrite' });
    fireEvent.click(within(first).getByRole('radio', { name: 'Skip' }));
    expect(all.getAttribute('aria-checked')).toBe('false');
    fireEvent.click(all);
    fireEvent.click(all);
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
    await waitFor(() => expect(service.copyProductCombo).toHaveBeenLastCalledWith(COMBO, ['p1', 'p2', 'p3'], []));
  });

  it('cannot copy when every pick would be skipped', async () => {
    service.copyProductCombo.mockResolvedValue(summary({ created: 0 }));
    mount();
    await pickAllAndNext();
    expect(screen.getByRole('button', { name: 'Copy' }).hasAttribute('disabled')).toBe(true);
    fireEvent.click(screen.getByRole('switch', { name: 'Overwrite all' }));
    expect(screen.getByRole('button', { name: 'Copy' }).hasAttribute('disabled')).toBe(false);
  });

  it('Back keeps the picks and writes nothing', async () => {
    mount();
    await pickAllAndNext();
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByText('3 products picked')).toBeTruthy();
    expect(service.copyProductCombo).toHaveBeenCalledTimes(1);
  });
});

describe('combo copy wording', () => {
  it('names products skipped for being a part, and missing template permission', () => {
    const lines = comboCopySummaryLines(
      'Bathtub Combo',
      summary({
        created: 2,
        skipped: [{ ...target('p9', 'ZZT-TAP-BL'), reason: 'part' }],
        conflicts: [],
        template_links_copied: false,
      }),
    );
    expect(lines).toContain('2 products get it as a new combo.');
    expect(lines).toContain('1 product is skipped because it is a part of this combo: ZZT-TAP-BL.');
    expect(lines).toContain('Price tag templates are not copied: that needs the permission to manage tag templates.');
  });

  it('the result toast counts created, overwritten and skipped', () => {
    expect(comboCopyResultLine(summary({ created: 2, overwritten: 1, skipped: [summary().skipped[0]] }))).toBe(
      'Combo copied: 2 created, 1 overwritten, 1 skipped.',
    );
    expect(comboCopyResultLine(summary({ created: 1, skipped: [], template_links_copied: false }))).toBe(
      'Combo copied: 1 created. Price tag templates were not copied.',
    );
  });
});

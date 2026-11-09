/**
 * ACC-COPY-TO-PRODUCTS: the "Copy to other products" button on a product's Accessories included card
 * and its picker / confirm dialog. Plan: documentation/plans/dealer-kit/PLAN-acc-copy-to-products-09nov.md.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const service = vi.hoisted(() => ({
  listOwnerAccessories: vi.fn(),
  replaceOwnerAccessories: vi.fn(),
  searchAccessories: vi.fn(),
  createAccessory: vi.fn(),
  copyProductAccessories: vi.fn(),
}));
const products = vi.hoisted(() => ({ getProducts: vi.fn() }));
const perms = vi.hoisted(() => ({ canEdit: true }));

vi.mock('../../../accessories/services/accessoryService', () => service);
vi.mock('../../services/productService', () => products);
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => perms.canEdit }));
vi.mock('../../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [{ id: 'c1', category_name: 'Bathtub' }], error: null, refetch: vi.fn() }),
}));
vi.mock('../../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [{ id: 'b1', brand_name: 'ZZT Brand' }], error: null, refetch: vi.fn() }),
}));
vi.mock('@/app/(protected)/dealer-kit/services/accessoryTemplateService', () => ({
  listAccessoryTemplates: vi.fn(async () => []),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/ui/rich-text-editor', () => ({ RichTextEditor: () => null, default: () => null }));
// The real list field is out of scope here; the card's own header is what is under test.
vi.mock('./AccessoryListField', () => ({ AccessoryListField: () => <div data-testid="list-field" /> }));

import { ProductAccessoriesSection } from './ProductAccessoriesSection';
import { CopyAccessoriesDialog, copySummaryLines } from './CopyAccessoriesDialog';

const SOURCE = 'p-source';

const row = (id: string, code: string) => ({
  id,
  product_code: code,
  product_name: `ZZT ${code}`,
  category_name: 'Bathtub',
  brand_name: 'ZZT Brand',
  is_active: true,
});

const PAGE = [row(SOURCE, 'ZZT-SRC'), row('p1', 'ZZT-TUB-1'), row('p2', 'ZZT-TUB-2')];

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function mountDialog(onOpenChange = vi.fn()) {
  render(
    <QueryClientProvider client={client()}>
      <CopyAccessoriesDialog open onOpenChange={onOpenChange} sourceProductId={SOURCE} entryCount={3} />
    </QueryClientProvider>,
  );
  return onOpenChange;
}

beforeEach(() => {
  vi.clearAllMocks();
  perms.canEdit = true;
  products.getProducts.mockResolvedValue({ data: PAGE, pagination: { total: 3, page: 1, limit: 25 } });
});

describe('Copy to other products button', () => {
  function mountSection() {
    render(
      <QueryClientProvider client={client()}>
        <ProductAccessoriesSection productId={SOURCE} />
      </QueryClientProvider>,
    );
  }

  it('shows for an editor once the list has an entry; the grid loads only when pressed', async () => {
    service.listOwnerAccessories.mockResolvedValue([{ id: 'a1' }]);
    mountSection();
    const button = await screen.findByRole('button', { name: /copy to other products/i });
    expect(products.getProducts).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(await screen.findByText('ZZT-TUB-1')).toBeTruthy();
    expect(screen.getByRole('dialog').textContent).toContain('Copy 1 entry to other products');
  });

  it('is hidden while the list is empty', async () => {
    service.listOwnerAccessories.mockResolvedValue([]);
    mountSection();
    await screen.findByTestId('list-field');
    expect(screen.queryByRole('button', { name: /copy to other products/i })).toBeNull();
  });

  it('is hidden from someone who cannot edit products', async () => {
    perms.canEdit = false;
    service.listOwnerAccessories.mockResolvedValue([{ id: 'a1' }]);
    mountSection();
    await screen.findByTestId('list-field');
    expect(screen.queryByRole('button', { name: /copy to other products/i })).toBeNull();
  });
});

describe('CopyAccessoriesDialog', () => {
  it('asks for active products only', async () => {
    mountDialog();
    await screen.findByText('ZZT-TUB-1');
    expect(products.getProducts).toHaveBeenCalledWith(expect.objectContaining({ status: 'active' }));
  });

  it('cannot tick the product being copied from', async () => {
    mountDialog();
    const box = await screen.findByRole('checkbox', { name: 'Select ZZT-SRC' });
    expect(box.hasAttribute('disabled') || box.getAttribute('data-disabled') !== null).toBe(true);
  });

  it('picks by hand, previews with a dry run, then copies', async () => {
    service.copyProductAccessories.mockImplementation(async (_s: string, ids: string[], dryRun?: boolean) => ({
      targets: ids.length,
      targets_with_a_list: 1,
      entries_added: 5,
      entries_already_there: 1,
      box_style_set: dryRun ? 1 : 1,
    }));
    const onOpenChange = mountDialog();

    const next = await screen.findByRole('button', { name: 'Next' });
    expect(next.hasAttribute('disabled')).toBe(true);

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select ZZT-TUB-1' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select ZZT-TUB-2' }));
    expect(screen.getByText('2 products picked')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() =>
      expect(service.copyProductAccessories).toHaveBeenCalledWith(SOURCE, ['p1', 'p2'], true),
    );
    const summary = await screen.findByTestId('copy-accessories-summary');
    expect(within(summary).getByText(/1 product already has a list: its entries stay/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
    await waitFor(() => expect(service.copyProductAccessories).toHaveBeenLastCalledWith(SOURCE, ['p1', 'p2']));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('Back from the confirm step keeps the picks and writes nothing', async () => {
    service.copyProductAccessories.mockResolvedValue({
      targets: 1, targets_with_a_list: 0, entries_added: 3, entries_already_there: 0, box_style_set: 0,
    });
    mountDialog();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select ZZT-TUB-1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await screen.findByTestId('copy-accessories-summary');
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByText('1 product picked')).toBeTruthy();
    expect(service.copyProductAccessories).toHaveBeenCalledTimes(1);
    expect(service.copyProductAccessories).toHaveBeenCalledWith(SOURCE, ['p1'], true);
  });

  it('"Select all" ticks every matching product except the source', async () => {
    products.getProducts.mockImplementation(async (params: { pageSize: number }) =>
      params.pageSize > 25
        ? { data: [...PAGE, row('p3', 'ZZT-TUB-3')], pagination: { total: 4, page: 1, limit: params.pageSize } }
        : { data: PAGE, pagination: { total: 4, page: 1, limit: 25 } },
    );
    mountDialog();
    await screen.findByText('ZZT-TUB-1');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows on this page' }));
    fireEvent.click(await screen.findByRole('button', { name: /select all 4 records/i }));
    expect(await screen.findByText('3 products picked')).toBeTruthy();
    expect(products.getProducts).toHaveBeenLastCalledWith(
      expect.objectContaining({ pageIndex: 0, pageSize: 501, status: 'active' }),
    );
  });
});

describe('CopyAccessoriesDialog columns', () => {
  it('reads Category and Brand from the nested objects the list endpoint sends', async () => {
    products.getProducts.mockResolvedValue({
      data: [{ id: 'p9', product_code: 'ZZT-NEST', product_name: 'ZZT nest', category: { category_name: 'ZZ Tubs' }, brand: { brand_name: 'ZZ Make' } }],
      pagination: { total: 1, page: 1, limit: 25 },
    });
    mountDialog();
    expect(await screen.findByText('ZZ Tubs')).toBeTruthy();
    expect(screen.getByText('ZZ Make')).toBeTruthy();
  });
});

describe('CopyAccessoriesDialog select all', () => {
  it('a search typed while "Select all" is fetching does not leave it stuck on "Selecting..."', async () => {
    let release: (v: unknown) => void = () => {};
    products.getProducts.mockImplementation((params: { pageSize: number }) =>
      params.pageSize > 25
        ? new Promise((resolve) => {
            release = resolve;
          })
        : Promise.resolve({ data: PAGE, pagination: { total: 4, page: 1, limit: 25 } }),
    );
    mountDialog();
    await screen.findByText('ZZT-TUB-1');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows on this page' }));
    fireEvent.click(await screen.findByRole('button', { name: /select all 4 records/i }));
    expect(await screen.findByText('Selecting...')).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText('Search products...'), { target: { value: 'TUB' } });
    await waitFor(() => expect(screen.queryByText('Selecting...')).toBeNull(), { timeout: 2000 });
    release({ data: [], pagination: { total: 0, page: 1, limit: 501 } });
  });
});

describe('copySummaryLines', () => {
  it('says what happens to products with and without a list', () => {
    expect(
      copySummaryLines({
        targets: 12, targets_with_a_list: 4, entries_added: 32, entries_already_there: 4, box_style_set: 8,
      }),
    ).toEqual([
      '12 products picked.',
      '8 products with no list get the whole list.',
      '4 products already have a list: their entries stay, the missing ones are added at the end.',
      '32 entries will be added, 4 entries already there are left as they are.',
      'The box style is set on 8 products that had none.',
    ]);
  });

  it('leaves out the lines that do not apply', () => {
    expect(
      copySummaryLines({ targets: 1, targets_with_a_list: 0, entries_added: 3, entries_already_there: 0, box_style_set: 0 }),
    ).toEqual(['1 product picked.', '1 product with no list gets the whole list.', '3 entries will be added.']);
  });
});

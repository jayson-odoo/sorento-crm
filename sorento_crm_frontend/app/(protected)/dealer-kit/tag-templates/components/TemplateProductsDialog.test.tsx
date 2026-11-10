/**
 * PRICETAG-TEMPLATE-PRODUCTS: the designer's Products dialog (mock v3, owner approved 10 Nov).
 * One view on the shared product picker (ProductTargetPicker.tsx): tick = uses this template.
 * Plan: documentation/plans/dealer-kit/PLAN-pricetag-template-products-10nov.md (Design v3).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const links = vi.hoisted(() => ({
  listTemplateProductIds: vi.fn(),
  assignTemplateToProducts: vi.fn(),
}));
const products = vi.hoisted(() => ({ getProducts: vi.fn() }));
const deferred = vi.hoisted(() => ({
  start: vi.fn(),
  input: null as Record<string, unknown> | null,
  isPending: false,
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock('../../services/productTagTemplateService', async (orig) => ({
  ...(await orig<typeof import('../../services/productTagTemplateService')>()),
  ...links,
}));
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => products);
vi.mock('@/lib/toast', () => ({ toast }));
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (input: Record<string, unknown>) => {
    deferred.input = input;
    return {
      start: deferred.start,
      cancel: vi.fn(),
      isPending: deferred.isPending,
      isBlocked: false,
      pending: null,
      countdown: null,
    };
  },
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [], error: null, refetch: vi.fn() }),
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [], error: null, refetch: vi.fn() }),
}));

import { TemplateProductsDialog } from './TemplateProductsDialog';

const T = 'tpl-1';
const row = (id: string, code: string) => ({
  id,
  product_code: code,
  product_name: `ZZT ${code}`,
  is_active: true,
});
const PAGE = [row('p1', 'SRTKS-7040-WH'), row('p2', 'SRTKS-7848-SS'), row('p3', 'SRTKS-8050-BK')];

function mount(onOpenChange = vi.fn(), warm?: string[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000 }, mutations: { retry: false } },
  });
  // The designer page already holds this query; `warm` stands in for that fresh cache.
  if (warm) client.setQueryData(['tag-template-product-ids', T], warm);
  render(
    <QueryClientProvider client={client}>
      <TemplateProductsDialog open onOpenChange={onOpenChange} templateId={T} templateName="Kitchen sink A6" />
    </QueryClientProvider>,
  );
  return { client, onOpenChange };
}

const box = (code: string) => screen.findByRole('checkbox', { name: `Select ${code}` });
const isTicked = (el: HTMLElement) =>
  el.getAttribute('aria-checked') === 'true' || el.getAttribute('data-state') === 'checked';

beforeEach(() => {
  vi.clearAllMocks();
  deferred.input = null;
  deferred.isPending = false;
  links.listTemplateProductIds.mockResolvedValue(['p1', 'p2']);
  links.assignTemplateToProducts.mockResolvedValue({ changed: 1 });
  products.getProducts.mockResolvedValue({ data: PAGE, pagination: { total: 3, page: 1, limit: 25 } });
});

describe('TemplateProductsDialog', () => {
  it('opens with the products that use the template already ticked, and no tabs', async () => {
    mount();
    await waitFor(async () => expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true));
    expect(isTicked(await box('SRTKS-7848-SS'))).toBe(true);
    expect(isTicked(await box('SRTKS-8050-BK'))).toBe(false);
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.getByText('2 use this template')).toBeTruthy();
    expect(screen.getByRole('heading', { name: /Kitchen sink A6/ }).className).toContain('pe-8');
  });

  it('Save stays off until something changes', async () => {
    mount();
    await waitFor(async () => expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true));
    expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('a tick adds, an untick removes, one Save applies both (removal parks with a countdown)', async () => {
    mount();
    await waitFor(async () => expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true));
    fireEvent.click(await box('SRTKS-8050-BK'));
    fireEvent.click(await box('SRTKS-7040-WH'));
    expect(screen.getByText('2 use this template after Save: 1 added, 1 removed')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(links.assignTemplateToProducts).toHaveBeenCalledWith(T, ['p3']));
    await waitFor(() => expect(deferred.start).toHaveBeenCalledWith({ product_ids: ['p1'] }));
    expect(deferred.input).toMatchObject({
      actionKey: 'tag_template.unassign_products',
      entityType: 'tag_template',
      entityId: T,
    });
  });

  it('adding only never parks anything', async () => {
    mount();
    await waitFor(async () => expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true));
    fireEvent.click(await box('SRTKS-8050-BK'));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(links.assignTemplateToProducts).toHaveBeenCalledWith(T, ['p3']));
    expect(deferred.start).not.toHaveBeenCalled();
  });

  it('removing only sends no add', async () => {
    mount();
    await waitFor(async () => expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true));
    fireEvent.click(await box('SRTKS-7848-SS'));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(deferred.start).toHaveBeenCalledWith({ product_ids: ['p2'] }));
    expect(links.assignTemplateToProducts).not.toHaveBeenCalled();
  });

  it('lists active products from the shared products list', async () => {
    mount();
    await box('SRTKS-7040-WH');
    expect(products.getProducts).toHaveBeenCalledWith(expect.objectContaining({ status: 'active' }));
    expect(products.getProducts).not.toHaveBeenCalledWith(
      expect.objectContaining({ tag_template_id: expect.anything() }),
    );
  });

  it('Select all adds the matching products to the ticks instead of replacing them, Clear goes back', async () => {
    // A page of two that does not hold seeded p1/p2; the page header tick (p3, p4) shows the banner,
    // and "Select all" brings p5 too.
    const pageRows = [row('p3', 'SRTKS-8050-BK'), row('p4', 'SRTKS-6045-SS')];
    products.getProducts.mockImplementation(async (params: { pageSize: number }) =>
      params.pageSize > 100
        ? { data: [...pageRows, row('p5', 'SRTKS-9050-SS')], pagination: { total: 3, page: 1, limit: 501 } }
        : { data: pageRows, pagination: { total: 30, page: 1, limit: 25 } },
    );
    mount();
    await box('SRTKS-8050-BK');
    await waitFor(() => expect(screen.getByText('2 use this template')).toBeTruthy());
    fireEvent.click(screen.getByRole('checkbox', { name: /select all/i }));
    expect(screen.getByText('4 use this template after Save: 2 added, 0 removed')).toBeTruthy();
    fireEvent.click(await screen.findByRole('button', { name: /Select all 30 records/ }));
    // Seeded p1 and p2 survive: Select all added, it did not replace.
    await waitFor(() =>
      expect(screen.getByText('5 use this template after Save: 3 added, 0 removed')).toBeTruthy(),
    );
    // Clear goes back to the ticks just before Select all, never to nothing.
    fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }));
    await waitFor(() =>
      expect(screen.getByText('4 use this template after Save: 2 added, 0 removed')).toBeTruthy(),
    );
  });

  it('the bulk strip Clear goes back to the links it opened with, never to nothing', async () => {
    mount();
    await waitFor(async () => expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true));
    fireEvent.click(await box('SRTKS-7040-WH'));
    fireEvent.click(await box('SRTKS-8050-BK'));
    expect(screen.getByText('2 use this template after Save: 1 added, 1 removed')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    await waitFor(() => expect(screen.getByText('2 use this template')).toBeTruthy());
    expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true);
    expect(isTicked(await box('SRTKS-8050-BK'))).toBe(false);
  });

  it('a seed that fails to load offers Retry and keeps Save off', async () => {
    links.listTemplateProductIds.mockRejectedValueOnce(new Error('boom'));
    mount();
    expect(await screen.findByText(/Could not load the products that use this template/)).toBeTruthy();
    fireEvent.click(await box('SRTKS-8050-BK'));
    expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.getByText(/use this template/)).toBeTruthy());
    expect(links.listTemplateProductIds).toHaveBeenCalledTimes(2);
  });

  it('says Linked as soon as the adds commit, before the removals start counting down', async () => {
    mount();
    await waitFor(async () => expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true));
    fireEvent.click(await box('SRTKS-8050-BK'));
    fireEvent.click(await box('SRTKS-7040-WH'));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(deferred.start).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith('Linked 1 product');
    const toastOrder = toast.success.mock.invocationCallOrder[0];
    expect(toastOrder).toBeLessThan(deferred.start.mock.invocationCallOrder[0]);
  });

  it('"Show: Uses this template" lists only the products that use it', async () => {
    mount();
    await waitFor(async () => expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true));
    // Radix opens on pointerdown, not click (same as SalesOrdersList.transferable.test.tsx).
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Filters/ }), { ctrlKey: false, button: 0 });
    fireEvent.click(await screen.findByText('Show: all products'));
    fireEvent.click(await screen.findByRole('option', { name: 'Uses this template' }));
    await waitFor(() =>
      expect(products.getProducts).toHaveBeenLastCalledWith(
        expect.objectContaining({ tag_template_id: T, status: 'active' }),
      ),
    );
  });

  it('a link made elsewhere while the dialog is open is neither a phantom add nor a phantom removal', async () => {
    links.listTemplateProductIds
      .mockResolvedValueOnce(['p1', 'p2'])
      .mockResolvedValue(['p1', 'p2', 'p3']); // someone links p3 on the product page meanwhile
    const { client } = mount();
    await waitFor(async () => expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true));
    await client.invalidateQueries({ queryKey: ['tag-template-product-ids', T] });
    await waitFor(() => expect(links.listTemplateProductIds).toHaveBeenCalledTimes(2));
    expect(screen.getByText('2 use this template')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('cannot be closed while the removals count down (it holds the only Cancel)', async () => {
    deferred.isPending = true;
    const { onOpenChange } = mount();
    await box('SRTKS-7040-WH');
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('seeds from a fresh fetch even when the page has the list cached and fresh', async () => {
    mount(vi.fn(), ['p1', 'p2']);
    await waitFor(() => expect(links.listTemplateProductIds).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByText('2 use this template')).toBeTruthy());
    expect(isTicked(await box('SRTKS-7040-WH'))).toBe(true);
  });
});

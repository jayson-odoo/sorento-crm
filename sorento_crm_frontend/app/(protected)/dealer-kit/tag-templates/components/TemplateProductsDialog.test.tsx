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
const deferred = vi.hoisted(() => ({ start: vi.fn(), input: null as Record<string, unknown> | null }));
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
    return { start: deferred.start, cancel: vi.fn(), isPending: false, isBlocked: false, pending: null, countdown: null };
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

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TemplateProductsDialog open onOpenChange={vi.fn()} templateId={T} templateName="Kitchen sink A6" />
    </QueryClientProvider>,
  );
}

const box = (code: string) => screen.findByRole('checkbox', { name: `Select ${code}` });
const isTicked = (el: HTMLElement) =>
  el.getAttribute('aria-checked') === 'true' || el.getAttribute('data-state') === 'checked';

beforeEach(() => {
  vi.clearAllMocks();
  deferred.input = null;
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
    // A page of two that does not hold seeded p1, so the page header tick shows the banner.
    products.getProducts.mockImplementation(async (params: { pageSize: number }) =>
      params.pageSize > 100
        ? { data: [row('p3', 'SRTKS-8050-BK'), row('p4', 'SRTKS-6045-SS')], pagination: { total: 2, page: 1, limit: 501 } }
        : { data: [row('p3', 'SRTKS-8050-BK'), row('p4', 'SRTKS-6045-SS')], pagination: { total: 30, page: 1, limit: 25 } },
    );
    mount();
    await box('SRTKS-8050-BK');
    await waitFor(() => expect(screen.getByText('2 use this template')).toBeTruthy());
    fireEvent.click(screen.getByRole('checkbox', { name: /select all/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Select all 30 records/ }));
    await waitFor(() =>
      expect(screen.getByText('4 use this template after Save: 2 added, 0 removed')).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }));
    await waitFor(() => expect(screen.getByText('2 use this template')).toBeTruthy());
  });
});

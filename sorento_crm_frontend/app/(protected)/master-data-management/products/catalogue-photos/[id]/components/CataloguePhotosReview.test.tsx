/**
 * The review page (CATALOG-IMAGES, AC-5, AC-9, AC-11, AC-17): tab counts, the Attach CTA, the
 * look-alike choice, attached rows locked, and the success toast.
 */
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

const perms = vi.hoisted(() => ({ granted: new Set<string>() }));
const svc = vi.hoisted(() => ({
  get: vi.fn(),
  list: vi.fn(),
  patch: vi.fn(),
  attach: vi.fn(),
}));
const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
const zip = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/master-data-management/products/catalogue-photos/r1',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.granted.has(slug),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: toasts.success, error: toasts.error } }));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title, actions }: { title: ReactNode; actions?: ReactNode }) => (
    <div>
      <h1>{title}</h1>
      {actions}
    </div>
  ),
}));
vi.mock('@/app/(protected)/resource-management/attachments/components/AttachmentBulkDownloadDialog', () => ({
  default: (props: Record<string, unknown>) => {
    zip.props = props;
    return null;
  },
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('../../../services/productService', () => ({
  getProductsForLineSelect: vi.fn().mockResolvedValue([]),
}));
vi.mock('../../../services/catalogPhotoReadingService', () => ({
  getCatalogPhotoReading: (...a: unknown[]) => svc.get(...a),
  listCatalogPhotos: (...a: unknown[]) => svc.list(...a),
  patchCatalogPhoto: (...a: unknown[]) => svc.patch(...a),
  attachCatalogPhotos: (...a: unknown[]) => svc.attach(...a),
}));

import { CataloguePhotosReview } from './CataloguePhotosReview';

function reading(over: Record<string, unknown> = {}) {
  return {
    id: 'r1',
    file_name: 'catalogue.pdf',
    status: 'ready',
    page_count: 32,
    photo_count: 7,
    error: null,
    directory_id: 'd1',
    created_at: '2026-10-27T10:00:00',
    created_by_name: 'Test User',
    counts: { ready: 4, duplicate: 2, needs_product: 1, skipped: 0, to_attach: 4 },
    attached_count: 0,
    ...over,
  };
}

function photo(over: Record<string, unknown> = {}) {
  return {
    id: 'p1',
    page: 2,
    position: 1,
    thumbnail_url: 'https://cdn.test/a.jpg',
    image_url: 'https://cdn.test/a.jpg',
    printed_code: 'SRTWT1906-BL-DIY',
    block_codes: ['SRTWT1906-BL-DIY'],
    placeholders: [],
    product: { id: 'prod1', product_code: 'SRTWT1906-BL-DIY' },
    rung: 'exact',
    confidence: 'high',
    suggestion: null,
    other_block_products: [],
    also_attach_product_ids: [],
    duplicate: null,
    decision: 'attach',
    attached_at: null,
    ...over,
  };
}

const page = (rows: unknown[]) => ({
  data: rows,
  empty: rows.length === 0,
  pagination: { total: rows.length, page: 1 },
});

function renderReview() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CataloguePhotosReview id="r1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  perms.granted = new Set(['master_data.products.edit']);
  Object.values(svc).forEach((m) => m.mockReset());
  toasts.success.mockReset();
  svc.get.mockResolvedValue(reading());
  svc.list.mockResolvedValue(page([photo()]));
  svc.patch.mockResolvedValue(photo());
});

describe('CataloguePhotosReview', () => {
  it('shows the four tabs with their counts and asks for the active tab only', async () => {
    renderReview();
    expect(await screen.findByRole('tab', { name: 'Ready (4)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Looks like an existing photo (2)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Needs a product (1)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Skipped (0)' })).toBeInTheDocument();
    await waitFor(() => expect(svc.list).toHaveBeenCalled());
    expect(svc.list.mock.calls[0][1]).toMatchObject({ tab: 'ready', pageIndex: 0, pageSize: 25 });

    svc.list.mockResolvedValue(page([]));
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Skipped (0)' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Skipped (0)' }));
    await waitFor(() =>
      expect(svc.list.mock.calls.some((c) => (c[1] as { tab: string }).tab === 'skipped')).toBe(true),
    );
    expect(await screen.findByText('Nothing skipped')).toBeInTheDocument();
  });

  it('reads "Attach N photos" from counts.to_attach and attaches on click, then toasts', async () => {
    svc.attach.mockResolvedValue({ attached: 3, replaced: 1, skipped: 2, products: 4 });
    renderReview();
    const button = await screen.findByRole('button', { name: 'Attach 4 photos' });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(svc.attach).toHaveBeenCalledWith('r1'));
    await waitFor(() =>
      expect(toasts.success).toHaveBeenCalledWith(
        'Attached 4 photos to 4 products. 1 replaced, 2 already on file.',
      ),
    );
  });

  it('disables Attach at 0 photos', async () => {
    svc.get.mockResolvedValue(reading({ counts: { ready: 0, duplicate: 0, needs_product: 0, skipped: 0, to_attach: 0 } }));
    renderReview();
    expect(await screen.findByRole('button', { name: 'Attach 0 photos' })).toBeDisabled();
  });

  it('disables Attach without master_data.products.edit', async () => {
    perms.granted = new Set();
    renderReview();
    expect(await screen.findByRole('button', { name: 'Attach 4 photos' })).toBeDisabled();
  });

  it('PATCHes the chosen decision on a look-alike row', async () => {
    const lookalike = photo({
      id: 'p9',
      decision: 'skip',
      duplicate: { attachment_id: 'a1', thumbnail_url: 'https://cdn.test/b.jpg', distance: 4 },
    });
    svc.list.mockImplementation(async (_id: string, params: { tab: string }) =>
      page(params.tab === 'duplicate' ? [lookalike] : [photo()]),
    );
    renderReview();
    fireEvent.mouseDown(await screen.findByRole('tab', { name: 'Looks like an existing photo (2)' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Looks like an existing photo (2)' }));
    fireEvent.click(await screen.findByRole('radio', { name: 'Replace' }));
    await waitFor(() =>
      expect(svc.patch).toHaveBeenCalledWith('r1', 'p9', { decision: 'replace' }),
    );
  });

  it('locks an attached row and reads Attached', async () => {
    svc.list.mockResolvedValue(page([photo({ attached_at: '2026-10-27T11:00:00' })]));
    renderReview();
    expect(await screen.findByText('Attached')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Skip' })).toBeNull();
  });

  it('shows the Attach step as done after a reload once everything is attached', async () => {
    svc.get.mockResolvedValue(
      reading({
        attached_count: 4,
        counts: { ready: 4, duplicate: 0, needs_product: 0, skipped: 0, to_attach: 0 },
      }),
    );
    renderReview();
    const current = await screen.findByRole('listitem', { current: 'step' });
    expect(current.textContent).toContain('Attach');
  });

  // ---- Fix round 1 (red) ----

  it('FR-8: Download all as ZIP sends the reading folder as folderIds', async () => {
    renderReview();
    fireEvent.click(await screen.findByRole('button', { name: /Download all as ZIP/ }));
    await waitFor(() => expect(zip.props?.open).toBe(true));
    expect(zip.props?.folderIds).toEqual(['d1']);
  });

  it('FR-10: the Product column header sorts by product_code', async () => {
    renderReview();
    const sortBy = async (name: RegExp) => {
      const header = await screen.findByRole('columnheader', { name });
      fireEvent.click(within(header).getAllByRole('button')[0]);
    };
    await sortBy(/Printed code/);
    await waitFor(() =>
      expect(
        svc.list.mock.calls.some((c) => (c[1] as { sort?: string }).sort === 'printed_code'),
      ).toBe(true),
    );
    await sortBy(/Product/);
    await waitFor(() =>
      expect(
        svc.list.mock.calls.some((c) => (c[1] as { sort?: string }).sort === 'product_code'),
      ).toBe(true),
    );
  });

  it('FR-14: an attached row on the look-alike tab reads Attached', async () => {
    const attachedDuplicate = photo({
      id: 'p8',
      decision: 'replace',
      attached_at: '2026-10-27T11:00:00',
      duplicate: { attachment_id: 'a1', thumbnail_url: 'https://cdn.test/b.jpg', distance: 4 },
    });
    svc.list.mockImplementation(async (_id: string, params: { tab: string }) =>
      page(params.tab === 'duplicate' ? [attachedDuplicate] : [photo()]),
    );
    renderReview();
    fireEvent.mouseDown(await screen.findByRole('tab', { name: 'Looks like an existing photo (2)' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Looks like an existing photo (2)' }));
    expect(await screen.findByText('Attached')).toBeInTheDocument();
  });

  it('FR-16: a placeholder is shown on the needs-a-product tab too', async () => {
    const unmatched = photo({
      id: 'p7',
      product: null,
      confidence: 'none',
      placeholders: ['SRTWB_____'],
    });
    svc.list.mockImplementation(async (_id: string, params: { tab: string }) =>
      page(params.tab === 'needs_product' ? [unmatched] : [photo()]),
    );
    renderReview();
    fireEvent.mouseDown(await screen.findByRole('tab', { name: 'Needs a product (1)' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Needs a product (1)' }));
    expect(await screen.findByText('SRTWB_____')).toBeInTheDocument();
  });

  // ---- Fix round 2 (red) ----

  it('FR-22: the ZIP dialog also receives the folder as directoryId', async () => {
    renderReview();
    fireEvent.click(await screen.findByRole('button', { name: /Download all as ZIP/ }));
    await waitFor(() => expect(zip.props?.open).toBe(true));
    expect(zip.props?.directoryId).toBe('d1');
  });

  it('FR-21: a row without a thumbnail renders no img element', async () => {
    svc.list.mockResolvedValue(page([photo({ thumbnail_url: null, image_url: null })]));
    renderReview();
    expect((await screen.findAllByText('SRTWT1906-BL-DIY')).length).toBeGreaterThan(0);
    expect(screen.queryByAltText('Page 2')).toBeNull();
    expect(document.querySelector('img')).toBeNull();
  });
});

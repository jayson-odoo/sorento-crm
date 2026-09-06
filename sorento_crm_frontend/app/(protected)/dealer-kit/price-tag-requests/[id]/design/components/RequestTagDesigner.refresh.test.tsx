/**
 * Re-resolving line data on focus/visibility (S2, AC-S2-1/2/3).
 *
 * `RequestTagDesigner.test.tsx` covers the designer's own state machine with a
 * richer mock setup this file deliberately keeps thin - the one thing under
 * test here is `refreshPricesSilently`: it must call `resolveRequestLines`
 * again on `window` `focus` and on `document` `visibilitychange` -> `visible`,
 * collapse the two into one call inside a 1s window, update `resolvedRows` on
 * success, and never touch `pricesStatus` (no loading flash, no error state)
 * on a failed background call.
 */

import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const push = vi.fn();
const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace, refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/price-tag-requests/req-1/design',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings', () => ({
  useKitLibrary: () => ({
    assetUrls: {},
    fonts: [],
    specKeys: [],
    fontOptions: [],
    reload: vi.fn(async () => {}),
    remember: vi.fn(),
  }),
}));

vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor', () => ({
  TagCanvasEditor: () => <div data-testid="canvas-editor">canvas open</div>,
}));

vi.mock('./ArrangeSheetView', () => ({
  ArrangeSheetView: () => <div data-testid="arrange-view">arrange open</div>,
}));

vi.mock('../../../../services/tagTemplateService', () => ({
  listPublishedTemplates: vi.fn(),
  createTemplateFromTag: vi.fn(),
}));
vi.mock('../../../../services/priceTagRequestService', () => ({
  resolveRequestLines: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
}));
vi.mock('../../../../tag-sizes/hooks/useTagSizes', () => ({
  useTagSizesQuery: () => ({ data: [] as unknown[] }),
  useDeleteTagSizePreset: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useCreateTagSize: () => ({ mutateAsync: vi.fn(async () => ({})), isPending: false }),
}));

import { listPublishedTemplates } from '../../../../services/tagTemplateService';
import { resolveRequestLines } from '../../../../services/priceTagRequestService';
import { RequestTagDesigner } from './RequestTagDesigner';
import type {
  PriceTagRequestDetail,
  PriceTagRequestLine,
} from '../../../../services/priceTagRequestService';
import type { LineTagData } from '@/lib/dealer-kit/tag-template-types';

const mockListTemplates = vi.mocked(listPublishedTemplates);
const mockResolveRequestLines = vi.mocked(resolveRequestLines);

function line(overrides: Partial<PriceTagRequestLine> = {}): PriceTagRequestLine {
  return {
    id: 'line-1',
    line_type: 'product',
    product_id: 'prod-1',
    product_set_id: null,
    name: 'Kitchen Sink',
    code: 'SRT-1234',
    show_promo_price: false,
    quantity: 1,
    alternatives: [],
    included_accessories: null,
    sort_order: 0,
    marketing_price_override: null,
    marketing_override_reason: null,
    list_price: 1599,
    sell_price: null,
    ...overrides,
  };
}

function request(overrides: Partial<PriceTagRequestDetail> = {}): PriceTagRequestDetail {
  return {
    id: 'req-1',
    doc_number: 'PT-000001',
    debtor_code: null,
    debtor_name: null,
    promotion_id: null,
    promotion_name: null,
    needed_by_date: null,
    notes: null,
    status: 'designing',
    line_count: 1,
    created_at: '2026-09-01T00:00:00Z',
    assigned_to_id: 'user-1',
    assigned_to_name: 'Jayson',
    contact_name: 'Ziv Beh',
    contact_id: 'contact-1',
    lines: [line()],
    ...overrides,
  };
}

function lineTagData(overrides: Partial<LineTagData> = {}): LineTagData {
  return {
    line_id: 'line-1',
    code: 'SRT-1234',
    name: 'Kitchen Sink',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: 'Stainless steel',
    specs: [],
    set_members: '',
    images: [],
    list_price: 1599,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    barcode: null,
    ...overrides,
  };
}

beforeEach(() => {
  mockListTemplates.mockReset();
  mockResolveRequestLines.mockReset();
  push.mockReset();
  replace.mockReset();
});

async function mount() {
  mockListTemplates.mockResolvedValue([]);
  mockResolveRequestLines.mockResolvedValue([lineTagData()]);

  render(
    <RequestTagDesigner
      request={request()}
      initialDoc={null}
      onSave={vi.fn(async () => {})}
      onAutosave={vi.fn(async () => {})}
    />,
  );
  await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
}

describe('RequestTagDesigner - background refresh on focus/visibility (S2)', () => {
  it('resolves again on window focus', async () => {
    await mount();
    expect(mockResolveRequestLines).toHaveBeenCalledTimes(1);

    mockResolveRequestLines.mockResolvedValueOnce([
      lineTagData({ barcode: '1234567890123' }),
    ]);
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
    });

    await waitFor(() => expect(mockResolveRequestLines).toHaveBeenCalledTimes(2));
    // The canvas stays mounted through the background refresh - no loading
    // flash, no error state swapped in over a working page.
    expect(screen.getByTestId('canvas-editor')).toBeInTheDocument();
  });

  it('resolves again when the document becomes visible', async () => {
    await mount();
    expect(mockResolveRequestLines).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() => expect(mockResolveRequestLines).toHaveBeenCalledTimes(2));
  });

  it('ignores a visibilitychange that leaves the tab hidden', async () => {
    await mount();
    expect(mockResolveRequestLines).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    });
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(mockResolveRequestLines).toHaveBeenCalledTimes(1);
  });

  it('collapses focus and visibilitychange firing together into one resolve call', async () => {
    await mount();
    expect(mockResolveRequestLines).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Both fired inside the same tick, well under the 1s guard.
    await waitFor(() => expect(mockResolveRequestLines).toHaveBeenCalledTimes(2));
    expect(mockResolveRequestLines).toHaveBeenCalledTimes(2);
  });

  it('a failing background refresh leaves the canvas exactly as it was', async () => {
    await mount();
    expect(mockResolveRequestLines).toHaveBeenCalledTimes(1);

    mockResolveRequestLines.mockRejectedValueOnce(new Error('network down'));
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
    });

    await waitFor(() => expect(mockResolveRequestLines).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId('canvas-editor')).toBeInTheDocument();
    expect(screen.queryByText('Failed to resolve prices.')).not.toBeInTheDocument();
  });

  it('does not resolve again on focus after unmount', async () => {
    const { unmount } = await (async () => {
      mockListTemplates.mockResolvedValue([]);
      mockResolveRequestLines.mockResolvedValue([lineTagData()]);
      const result = render(
        <RequestTagDesigner
          request={request()}
          initialDoc={null}
          onSave={vi.fn(async () => {})}
          onAutosave={vi.fn(async () => {})}
        />,
      );
      await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
      return result;
    })();

    unmount();
    mockResolveRequestLines.mockClear();

    window.dispatchEvent(new Event('focus'));

    expect(mockResolveRequestLines).not.toHaveBeenCalled();
  });
});

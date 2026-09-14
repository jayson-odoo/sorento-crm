/**
 * Re-resolving line data on focus/visibility (S2, AC-S2-1/2/3).
 *
 * `RequestTagDesigner.test.tsx` covers the designer's own state machine with a
 * richer mock setup this file deliberately keeps thin - the one thing under
 * test here is `refreshPricesSilently`: it must call `resolveRequestTags`
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
  // One row per TAG since S3 (D3) - `resolveRequestTags` is gone with the
  // line-keyed document. The three beside it are what the rail's Split / Pick
  // one actions and the post-split reload call.
  resolveRequestTags: vi.fn(),
  getPriceTagRequest: vi.fn(),
  splitRequestTag: vi.fn(),
  updateRequestTag: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
}));
vi.mock('../../../../tag-sizes/hooks/useTagSizes', () => ({
  useTagSizesQuery: () => ({ data: [] as unknown[] }),
  useDeleteTagSizePreset: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useCreateTagSize: () => ({ mutateAsync: vi.fn(async () => ({})), isPending: false }),
}));

import { listPublishedTemplates } from '../../../../services/tagTemplateService';
import { resolveRequestTags } from '../../../../services/priceTagRequestService';
import { RequestTagDesigner } from './RequestTagDesigner';
import type {
  PriceTagRequestDetail,
  PriceTagRequestLine,
  PriceTagRequestTag,
} from '../../../../services/priceTagRequestService';
import type { LineTagData } from '@/lib/dealer-kit/tag-template-types';

const mockListTemplates = vi.mocked(listPublishedTemplates);
const mockResolveRequestTags = vi.mocked(resolveRequestTags);

/**
 * The rail row label for a line's default tag.
 *
 * The product builds "1a"/"1b" from the line's position plus a letter; a
 * fixture only needs two lines' tag rows to be separately clickable, so the
 * label reuses the line id's own suffix ('line-b' -> 'ba'). The rail selects a
 * TAG now, not a line - the line header is no longer a button - so every test
 * that used to click a line's code or name clicks its tag row instead.
 */
function tagLabelFor(lineId: string): string {
  return `${lineId.split('-').pop() ?? '1'}a`;
}

/**
 * The one tag a line carries by default (S3, AC-S3-1).
 *
 * Its id IS the line id, so every id these tests already assert on stays the
 * id they assert on: submit mints exactly one tag per line, and only a Split
 * ever gives a line a second one.
 */
function requestTag(
  lineId: string,
  quantity: number,
  overrides: Partial<PriceTagRequestTag> = {},
): PriceTagRequestTag {
  return {
    id: lineId,
    sort_order: 0,
    label: tagLabelFor(lineId),
    quantity,
    choices: {},
    choices_display: [],
    open_groups: [],
    marketing_price_override: null,
    marketing_override_reason: null,
    list_price: 1599,
    sell_price: null,
    ...overrides,
  };
}

function line(overrides: Partial<PriceTagRequestLine> = {}): PriceTagRequestLine {
  const merged = {
    id: 'line-1',
    line_type: 'product' as const,
    product_id: 'prod-1' as string | null,
    product_set_id: null as string | null,
    name: 'Kitchen Sink',
    code: 'SRT-1234',
    show_promo_price: false,
    quantity: 1,
    included_accessories: null as string | null,
    sort_order: 0,
    list_price: 1599 as number | null,
    sell_price: null as number | null,
    parts: [],
    package_warning: null,
    ...overrides,
  };
  return {
    ...merged,
    tags: overrides.tags ?? [requestTag(merged.id, merged.quantity)],
  } as PriceTagRequestLine;
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
  // One row per TAG since S3. The everyday request has one tag per line and the
  // tag's id is the line's, so a row named by `line_id` keys on the same id it
  // always did.
  const lineId = overrides.line_id ?? 'line-1';
  return {
    tag_id: lineId,
    tag_label: '1a',
    open_groups: [],
    parts: [],
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
  mockResolveRequestTags.mockReset();
  push.mockReset();
  replace.mockReset();
});

async function mount() {
  mockListTemplates.mockResolvedValue([]);
  mockResolveRequestTags.mockResolvedValue([lineTagData()]);

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
    expect(mockResolveRequestTags).toHaveBeenCalledTimes(1);

    mockResolveRequestTags.mockResolvedValueOnce([
      lineTagData({ barcode: '1234567890123' }),
    ]);
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
    });

    await waitFor(() => expect(mockResolveRequestTags).toHaveBeenCalledTimes(2));
    // The canvas stays mounted through the background refresh - no loading
    // flash, no error state swapped in over a working page.
    expect(screen.getByTestId('canvas-editor')).toBeInTheDocument();
  });

  it('resolves again when the document becomes visible', async () => {
    await mount();
    expect(mockResolveRequestTags).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() => expect(mockResolveRequestTags).toHaveBeenCalledTimes(2));
  });

  it('ignores a visibilitychange that leaves the tab hidden', async () => {
    await mount();
    expect(mockResolveRequestTags).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    });
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(mockResolveRequestTags).toHaveBeenCalledTimes(1);
  });

  it('collapses focus and visibilitychange firing together into one resolve call', async () => {
    await mount();
    expect(mockResolveRequestTags).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Both fired inside the same tick, well under the 1s guard.
    await waitFor(() => expect(mockResolveRequestTags).toHaveBeenCalledTimes(2));
    expect(mockResolveRequestTags).toHaveBeenCalledTimes(2);
  });

  it('a failing background refresh leaves the canvas exactly as it was', async () => {
    await mount();
    expect(mockResolveRequestTags).toHaveBeenCalledTimes(1);

    mockResolveRequestTags.mockRejectedValueOnce(new Error('network down'));
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
    });

    await waitFor(() => expect(mockResolveRequestTags).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId('canvas-editor')).toBeInTheDocument();
    expect(screen.queryByText('Failed to resolve prices.')).not.toBeInTheDocument();
  });

  it('does not resolve again on focus after unmount', async () => {
    const { unmount } = await (async () => {
      mockListTemplates.mockResolvedValue([]);
      mockResolveRequestTags.mockResolvedValue([lineTagData()]);
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
    mockResolveRequestTags.mockClear();

    window.dispatchEvent(new Event('focus'));

    expect(mockResolveRequestTags).not.toHaveBeenCalled();
  });
});

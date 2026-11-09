/**
 * SPEC-VALUE-ICONS: the tab hands the table its price-tag icons, so each row shows the icons its
 * saved value carries (owner 9 Nov, 1a). Same mocks as the verification suite; `SpecTable` is a
 * stub that calls the adornment for one row.
 */
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ProductSpecificationsTab from './ProductSpecificationsTab';
import type { ProductSpecDetail } from '../../../product-specifications/types/productSpec.types';
import type { VerificationBlock } from '../../../spec-verification/types/specVerification.types';

vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    custom: vi.fn(),
    message: vi.fn(),
    // The pending-entity store takes its own countdown toast down once the parked
    // action settles - without this the store's follow-through timer throws an
    // unhandled rejection if it fires after the test ends.
    dismiss: vi.fn(),
  },
}));

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// The table stub calls the tab's adornment for one fixed row, the way the real table does per row.
vi.mock('@/components/spec-table', () => ({
  SpecTable: ({ valueAdornment }: { valueAdornment?: (row: unknown) => ReactNode }) => (
    <div data-testid="spec-table-stub">
      {valueAdornment?.({
        specKey: 'water_supply',
        label: 'Water supply',
        value: 'mixer',
        unit: null,
        dataType: 'text',
        options: [],
        source: 'derived',
        evidence: null,
        unknownKey: false,
        valueLabels: {},
        conflict: null,
      })}
    </div>
  ),
  AddSpecificationDialog: () => null,
}));

const iconsFor = vi.fn();
vi.mock('../../hooks/useSpecValueIcons', () => ({
  useSpecValueIcons: () => ({ iconsFor, canManage: false }),
}));

const usePermissions = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => usePermissions(),
}));

const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'spec_verification.unverify',
  entity_type: 'spec_verification',
  entity_id: 'WC100',
  // Five seconds out from "now" - a fixed past timestamp reads as already
  // lapsed and disables the countdown's own Cancel button.
  commit_at: new Date(Date.now() + 5000).toISOString(),
  window_seconds: 5,
});
const cancelPendingAction = vi.fn().mockResolvedValue({});
const getCurrentPendingAction = vi.fn().mockResolvedValue({ pending: null, last_outcome: null });
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: (...args: unknown[]) => cancelPendingAction(...args),
  getCurrentPendingAction: (...args: unknown[]) => getCurrentPendingAction(...args),
}));

const verify = vi.fn();
const useProductSpecTable = vi.fn();
vi.mock('../../hooks/useProductSpecTable', () => ({
  DETAIL_KEY: (productId: string) => ['product-spec-detail', productId],
  useProductSpecTable: (...a: unknown[]) => useProductSpecTable(...a),
}));

vi.mock('../../hooks/useProducts', () => ({
  useProduct: () => ({
    data: { id: 'p-1', product_code: 'WC100', product_name: 'WC100', list_price: null, price_tag_description: null },
    isLoading: false,
  }),
  useUpdateProduct: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

function baseDetail(verification: VerificationBlock): ProductSpecDetail {
  return {
    product_id: 'p-1',
    product_code: 'WC100',
    category_code: 'BR-KS',
    searchable: true,
    diagnosis: {
      reason: 'eligible',
      class_label: 'Kitchen Sink',
      brand_hint: 'Sorento',
      suffix: null,
    },
    spec: {
      values: { shape: { value: 'round' } },
      provenance: {
        shape: { source: 'human', confidence: 1, evidence: 'manual' },
      },
      rendered_text: 'A round kitchen sink',
      status: 'authored',
      derived_at: '2026-08-01T09:00:00',
    },
    exceptions: [],
    source_text: 'WC100 round sink',
    verification,
    values_hash: 'hash-1',
  } as ProductSpecDetail;
}

/** `useDeferredAction` inside `CheckedLine` is real (only the service is mocked), so
 * it needs a live `QueryClient` under it - same as `SpecVisibilitySection.test.tsx`. */
function renderTab(productId = 'p-1') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <ProductSpecificationsTab productId={productId} />
      </QueryClientProvider>,
    ),
  };
}

function mockHook(
  detail: ProductSpecDetail,
  overrides: Partial<ReturnType<typeof useProductSpecTable>> = {},
) {
  useProductSpecTable.mockReturnValue({
    detail,
    rows: [],
    registry: [
      {
        spec_key: 'shape',
        label: 'Shape',
        data_type: 'enum',
        unit: null,
        allowed_values: [],
        synonyms: {},
      },
      {
        spec_key: 'dim_height',
        label: 'Height',
        data_type: 'numeric',
        unit: 'mm',
        allowed_values: [],
        synonyms: {},
      },
      {
        spec_key: 'finish',
        label: 'Finish or colour',
        data_type: 'enum',
        unit: null,
        allowed_values: [],
        synonyms: {},
      },
    ],
    applicableKeys: [],
    otherKeys: [],
    heldKeys: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    verify,
    verificationBusy: false,
    setValue: vi.fn(),
    tombstone: vi.fn(),
    revert: vi.fn(),
    addValue: vi.fn(),
    createKey: vi.fn(),
    checkSimilarKey: vi.fn(),
    ...overrides,
  });
}





beforeEach(() => {
  vi.clearAllMocks();
  usePermissions.mockReturnValue({
    permissionSet: new Set(['master_data.products.edit']),
  });
});

afterEach(() => cleanup());

describe('ProductSpecificationsTab value icons', () => {
  beforeEach(() => {
    usePermissions.mockReturnValue({ permissionSet: new Set(['master_data.products.view']), isLoading: false });
    iconsFor.mockReset().mockReturnValue([
      { id: 'hot', name: 'Hot water', spec_key: 'water_supply', values: ['mixer'], url: 'https://cdn/hot.png' },
    ]);
  });
  afterEach(() => cleanup());

  it("draws the icons the row's value carries inside the table", () => {
    mockHook(
      baseDetail({
        state: 'unverified',
        verified_by_name: null,
        verified_at: null,
        invalidated_at: null,
        invalidated_reason: null,
        invalidated_by_name: null,
        invalidated_diff: null,
      }),
    );
    renderTab();
    const table = screen.getByTestId('spec-table-stub');
    const icon = table.querySelector('[data-spec-icon="hot"]');
    expect(icon).toBeTruthy();
    expect(icon?.getAttribute('title')).toBe('Hot water');
    expect(iconsFor).toHaveBeenCalledWith(expect.objectContaining({ specKey: 'water_supply', value: 'mixer' }));
  });
});

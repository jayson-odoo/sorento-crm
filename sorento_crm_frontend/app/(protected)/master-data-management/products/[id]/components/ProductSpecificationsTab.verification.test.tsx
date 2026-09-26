/**
 * ProductSpecificationsTab - the checked line (AC-S2.3, AC-S2.4).
 *
 * `useProductSpecTable` is mocked so the test drives the tab's rendering directly off
 * a `VerificationBlock`, the way the real hook would hand it back from
 * `GET /by-product/{id}`. `SpecTable` / `AddSpecificationDialog` are stubbed: heavy,
 * and already covered by their own suite.
 *
 * Rewritten for the plain wording (AC-S2.3: "Not checked yet" / "Checked by {name}
 * on {date}" / "Needs checking again") and, since fix round 1, the SERVER-deferred
 * Undo (AC-S2.4, D7): `spec_verification.unverify` through `useDeferredAction` -
 * `pendingActionService` is mocked rather than the hook itself, the same way
 * `SpecVisibilitySection.test.tsx` drives its own deferred action. The confirm
 * `AlertDialog` this file used to assert is retired (D7).
 */
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
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

vi.mock('@/components/spec-table', () => ({
  SpecTable: () => <div data-testid="spec-table-stub" />,
  AddSpecificationDialog: () => null,
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

const UNVERIFIED: VerificationBlock = {
  state: 'unverified',
  verified_by_name: null,
  verified_at: null,
  invalidated_at: null,
  invalidated_reason: null,
  invalidated_by_name: null,
  invalidated_diff: null,
};

const VERIFIED: VerificationBlock = {
  state: 'verified',
  verified_by_name: 'Jay Odoo',
  verified_at: '2026-08-10T09:00:00',
  invalidated_at: null,
  invalidated_reason: null,
  invalidated_by_name: null,
  invalidated_diff: null,
};

const NEEDS_REVERIFY: VerificationBlock = {
  state: 'needs_reverify',
  verified_by_name: 'Jay Odoo',
  verified_at: '2026-08-01T09:00:00',
  invalidated_at: '2026-08-10T10:00:00',
  invalidated_reason: 'values_changed',
  invalidated_by_name: null,
  invalidated_diff: {
    changed: [
      { spec_key: 'shape', was: { value: 'round' }, now: { value: 'square' } },
      {
        spec_key: 'dim_height',
        was: { value: 770, unit: 'mm' },
        now: { value: 800, unit: 'mm' },
      },
      { spec_key: 'finish', was: null, now: { value: 'matte_black' } },
    ],
  },
};

const MANUAL_UNVERIFY: VerificationBlock = {
  state: 'unverified',
  verified_by_name: 'Jay Odoo',
  verified_at: '2026-08-01T09:00:00',
  invalidated_at: '2026-08-11T11:00:00',
  invalidated_reason: 'manual_unverify',
  invalidated_by_name: 'Alice Tan',
  invalidated_diff: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  usePermissions.mockReturnValue({
    permissionSet: new Set(['master_data.products.edit']),
  });
});

afterEach(() => cleanup());

describe('CheckedLine - renders in every state (AC-S2.3)', () => {
  it('unverified: "Not checked yet", Mark as checked offered', () => {
    mockHook(baseDetail(UNVERIFIED));
    renderTab();

    expect(screen.getByText('Not checked yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark as checked' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
  });

  it('verified: "Checked by {name} on {date}", Undo offered', () => {
    mockHook(baseDetail(VERIFIED));
    renderTab();

    expect(screen.getByText(/^Checked by Jay Odoo on /)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark as checked' })).not.toBeInTheDocument();
  });

  it('needs_reverify: "Needs checking again", the diff renders, Mark as checked offered', () => {
    mockHook(baseDetail(NEEDS_REVERIFY));
    renderTab();

    expect(screen.getByText('Needs checking again')).toBeInTheDocument();
    expect(screen.getByText('What moved since it was checked')).toBeInTheDocument();
    expect(screen.getByText('Shape')).toBeInTheDocument();
    expect(screen.getByText('Round')).toBeInTheDocument();
    expect(screen.getByText('Square')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark as checked' })).toBeInTheDocument();
  });

  it('a diff entry renders its readable value, with the unit, never [object Object]', () => {
    mockHook(baseDetail(NEEDS_REVERIFY));
    const { container } = renderTab();

    expect(screen.getByText('Height')).toBeInTheDocument();
    expect(screen.getByText('770 mm')).toBeInTheDocument();
    expect(screen.getByText('800 mm')).toBeInTheDocument();
    expect(screen.getByText('Finish or colour')).toBeInTheDocument();
    expect(screen.getByText('nothing')).toBeInTheDocument();
    expect(screen.getByText('Matte black')).toBeInTheDocument();

    const strip = container.querySelector('[data-spec-verification]') as HTMLElement;
    expect(strip.textContent).not.toContain('[object Object]');
  });

  it('manual_unverify: "Withdrawn by" line names the withdrawer and keeps the original stamp', () => {
    mockHook(baseDetail(MANUAL_UNVERIFY));
    renderTab();

    expect(screen.getByText('Not checked yet')).toBeInTheDocument();
    expect(screen.getByText(/^Withdrawn by Alice Tan, /)).toBeInTheDocument();
  });
});

describe('Mark as checked / Undo visibility gated on master_data.products.edit', () => {
  it('hides both actions without the edit grant, even though the line still renders', () => {
    usePermissions.mockReturnValue({
      permissionSet: new Set(['master_data.products.view']),
    });
    mockHook(baseDetail(VERIFIED));
    renderTab();

    expect(screen.getByText(/^Checked by Jay Odoo on /)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark as checked' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
  });
});

describe('Undo is a server-deferred action, never a confirm dialog (AC-S2.4, D7)', () => {
  it('pressing Undo parks spec_verification.unverify on the server, keyed by the product code', async () => {
    mockHook(baseDetail(VERIFIED));
    renderTab();

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledWith({
      actionKey: 'spec_verification.unverify',
      entityType: 'spec_verification',
      entityId: 'WC100',
      payload: undefined,
    }));

    expect(screen.queryByText('Confirm unverify')).not.toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('timer')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    // The window is 5s, server-side (WINDOW_REVERSIBLE) - this tab never runs its own timer.
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
  });

  it('Cancel withdraws the parked action without applying it', async () => {
    mockHook(baseDetail(VERIFIED));
    renderTab();

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(screen.getByRole('timer')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(cancelPendingAction).toHaveBeenCalledWith('pa-1'));
  });
});

describe('Mark as checked action', () => {
  it('a single press calls verify() with no confirmation gate', () => {
    mockHook(baseDetail(NEEDS_REVERIFY));
    renderTab();

    fireEvent.click(screen.getByRole('button', { name: 'Mark as checked' }));

    expect(verify).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Confirm verify')).not.toBeInTheDocument();
  });
});

describe('Exceptions are not a thing the user is shown (captain ruling 2026-08-17)', () => {
  it('renders no exceptions section and no per-exception Edit, even when the product has one', () => {
    const detail = baseDetail(UNVERIFIED);
    detail.exceptions = [
      {
        id: 'exc-1',
        spec_key: 'shape',
        reason: 'shape_mismatch',
        proposed: { value: 'square' },
        stored: { value: 'round' },
      },
    ];
    mockHook(detail);
    renderTab();

    expect(screen.queryByText(/Needs a human/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.getByTestId('spec-table-stub')).toBeInTheDocument();
  });
});

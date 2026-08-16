/**
 * ProductSpecificationsTab — the verification block (PR 3, AC-D.13/D.19/D.20/D.25).
 *
 * `useProductSpecTable` is mocked so the test drives the tab's rendering directly off
 * a `VerificationBlock`, the way the real hook would hand it back from
 * `GET /by-product/{id}`. `SpecTable` / `AddSpecificationDialog` are stubbed to a
 * capture shim: heavy, already covered by their own suite, and here we only need to
 * assert the ONE prop that matters — `openEditorFor` — following the exception row's
 * own "Edit" button (AC-D.17c).
 */
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import ProductSpecificationsTab from './ProductSpecificationsTab';
import type { ProductSpecDetail } from '../../../product-specifications/types/productSpec.types';
import type { VerificationBlock } from '../../../spec-verification/types/specVerification.types';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const capturedSpecTableProps = vi.hoisted(() => ({ openEditorFor: undefined as string | null | undefined }));

vi.mock('@/components/spec-table', () => ({
  SpecTable: (props: { openEditorFor?: string | null }) => {
    capturedSpecTableProps.openEditorFor = props.openEditorFor;
    return <div data-testid="spec-table-stub" />;
  },
  AddSpecificationDialog: () => null,
}));

const usePermissions = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => usePermissions(),
}));

const verify = vi.fn();
const unverify = vi.fn();
const useProductSpecTable = vi.fn();
vi.mock('../../hooks/useProductSpecTable', () => ({
  useProductSpecTable: (...a: unknown[]) => useProductSpecTable(...a),
}));

function baseDetail(verification: VerificationBlock): ProductSpecDetail {
  return {
    product_id: 'p-1',
    product_code: 'WC100',
    category_code: 'BR-KS',
    searchable: true,
    diagnosis: { reason: 'eligible', class_label: 'Kitchen Sink', brand_hint: 'Sorento', suffix: null },
    spec: {
      values: { shape: { value: 'round' } },
      provenance: { shape: { source: 'human', confidence: 1, evidence: 'manual' } },
      rendered_text: 'A round kitchen sink',
      status: 'authored',
      derived_at: '2026-08-01T09:00:00',
    },
    exceptions: [],
    source_text: 'WC100 round sink',
    flyer_text: null,
    verification,
    values_hash: 'hash-1',
  } as ProductSpecDetail;
}

function mockHook(detail: ProductSpecDetail, overrides: Partial<ReturnType<typeof useProductSpecTable>> = {}) {
  useProductSpecTable.mockReturnValue({
    detail,
    rows: [],
    registry: [
      { spec_key: 'shape', label: 'Shape', data_type: 'enum', unit: null, allowed_values: [], synonyms: {} },
    ],
    applicableKeys: [],
    otherKeys: [],
    heldKeys: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    verify,
    unverify,
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
  invalidated_diff: { changed: [{ spec_key: 'shape', was: 'round', now: 'square' }] },
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
  usePermissions.mockReturnValue({ permissionSet: new Set(['master_data.products.edit']) });
  capturedSpecTableProps.openEditorFor = undefined;
});

afterEach(() => cleanup());

describe('VerificationStrip — renders in every state', () => {
  it('unverified: pill reads Unverified, no stamp line, Verify button offered', () => {
    mockHook(baseDetail(UNVERIFIED));
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('Unverified')).toBeInTheDocument();
    expect(screen.queryByText(/^by /)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verify' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Unverify' })).not.toBeInTheDocument();
  });

  it('verified: pill reads Verified, who+when stamp line, Unverify button offered', () => {
    mockHook(baseDetail(VERIFIED));
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.getByText(/by Jay Odoo, /)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Unverify' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Verify' })).not.toBeInTheDocument();
  });

  it('needs_reverify: pill reads Needs re-verify, was/now diff rows render, Verify offered', () => {
    mockHook(baseDetail(NEEDS_REVERIFY));
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('Needs re-verify')).toBeInTheDocument();
    expect(screen.getByText(/by Jay Odoo, /)).toBeInTheDocument();
    expect(screen.getByText('What moved since it was verified')).toBeInTheDocument();
    expect(screen.getByText('Shape')).toBeInTheDocument();
    expect(screen.getByText('Round')).toBeInTheDocument();
    expect(screen.getByText('Square')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verify' })).toBeInTheDocument();
  });

  it('manual_unverify: "Withdrawn by" line names the withdrawer and keeps the original stamp', () => {
    mockHook(baseDetail(MANUAL_UNVERIFY));
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('Unverified')).toBeInTheDocument();
    expect(screen.getByText(/by Jay Odoo, /)).toBeInTheDocument(); // original verifier preserved
    expect(screen.getByText(/^Withdrawn by Alice Tan, /)).toBeInTheDocument();
  });
});

describe('Verify / Unverify visibility gated on master_data.products.edit', () => {
  it('hides both actions without the edit grant, even though the pill still renders', () => {
    usePermissions.mockReturnValue({ permissionSet: new Set(['master_data.products.view']) });
    mockHook(baseDetail(VERIFIED));
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Verify' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Unverify' })).not.toBeInTheDocument();
  });
});

describe('Unverify confirmation', () => {
  it('the AlertDialog copy names the product code and calls unverify() on confirm', async () => {
    mockHook(baseDetail(VERIFIED));
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(screen.getByRole('button', { name: 'Unverify' }));

    expect(screen.getByText('Confirm unverify')).toBeInTheDocument();
    expect(screen.getByText(/This withdraws the verification for WC100\./)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Unverify' }));
    expect(unverify).toHaveBeenCalledTimes(1);
  });

  it('cancel dismisses the dialog without calling unverify()', () => {
    mockHook(baseDetail(VERIFIED));
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(screen.getByRole('button', { name: 'Unverify' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByText('Confirm unverify')).not.toBeInTheDocument();
    expect(unverify).not.toHaveBeenCalled();
  });
});

describe('Verify action', () => {
  it('single Verify calls verify() with no confirmation gate', () => {
    mockHook(baseDetail(NEEDS_REVERIFY));
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(screen.getByRole('button', { name: 'Verify' }));

    expect(verify).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Confirm verify')).not.toBeInTheDocument();
  });
});

describe('Exception row Edit opens the SpecTable editor for that key (AC-D.17c)', () => {
  it('clicking Edit on an exception row passes that spec_key as openEditorFor', () => {
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
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(capturedSpecTableProps.openEditorFor).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    expect(capturedSpecTableProps.openEditorFor).toBe('shape');
  });

  it('renders the exceptions card even when there are none, per the never-hide-a-section rule', () => {
    mockHook(baseDetail(UNVERIFIED));
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('Needs a human (0)')).toBeInTheDocument();
    expect(
      screen.getByText('Nothing on this product disagrees with itself.'),
    ).toBeInTheDocument();
  });
});

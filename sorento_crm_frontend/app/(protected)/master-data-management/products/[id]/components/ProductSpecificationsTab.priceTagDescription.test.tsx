/**
 * ProductSpecificationsTab - the price tag description is a per-product
 * TEMPLATE now (PLAN-price-tag-r10.md S11, owner amendment 21 Sep, amends
 * S4): edited in place on THIS tab, directly under "Product description",
 * with the same Insert field picker the tag template designer uses, and
 * previewed rendered for THIS product's own spec values before it is ever
 * saved. The Overview edit form and Overview detail row are gone (see
 * `ProductForm.priceTagDescription.test.tsx` /
 * `ProductDetail.priceTagDescription.test.tsx`) - this is the one home.
 *
 * `useProductSpecTable` and `usePermissions` are mocked exactly as
 * `ProductSpecificationsTab.verification.test.tsx` already does. New here:
 * `useProduct`/`useUpdateProduct` (`../../hooks/useProducts`) are mocked too
 * - the SAME hook `ProductForm.tsx` already saves every other product edit
 * through, and the SAME `['product', id]` query `ProductDetail.tsx` already
 * populates when it mounts this tab (AC-S4-10, S11 design point 2).
 * `InsertFieldDialog` is left REAL (not stubbed): the group-restriction
 * assertion below has to see what it actually renders.
 *
 * Written test-FIRST: `ProductSpecificationsTab.tsx` has no such block, no
 * `useProduct`/`useUpdateProduct` call and no Insert field wiring at all
 * yet - it renders "Product description" alone. Every test here is red on a
 * missing element.
 */
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ProductSpecificationsTab from './ProductSpecificationsTab';
import type { ProductSpecDetail } from '../../../product-specifications/types/productSpec.types';
import type { VerificationBlock } from '../../../spec-verification/types/specVerification.types';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
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

// The extraction panel is its own feature with its own suite; it fetches
// through react-query, which this test deliberately does not provide.
vi.mock('./SpecExtractPanel', () => ({ default: () => null }));

const usePermissions = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => usePermissions(),
}));

// `CheckedLine` parks the real `spec_verification.unverify` deferred action
// (fix round 1) - nothing here exercises it, so the service only needs to
// resolve to "nothing pending" without ever being asked to create one.
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

const useProductSpecTable = vi.fn();
vi.mock('../../hooks/useProductSpecTable', () => ({
  DETAIL_KEY: (productId: string) => ['product-spec-detail', productId],
  useProductSpecTable: (...a: unknown[]) => useProductSpecTable(...a),
}));

// AC-S4-10/S11: `useProduct` supplies name/list_price/`price_tag_description`
// to a component that until now only ever knew the product id;
// `useUpdateProduct` is the SAME mutation hook `ProductForm.tsx` already
// saves every other product field through.
const updateMutateAsync = vi.fn().mockResolvedValue({});
const useProduct = vi.fn();
vi.mock('../../hooks/useProducts', () => ({
  useProduct: (...a: unknown[]) => useProduct(...a),
  useUpdateProduct: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
}));

const VERIFIED: VerificationBlock = {
  state: 'verified',
  verified_by_name: 'Jay Odoo',
  verified_at: '2026-08-10T09:00:00',
  invalidated_at: null,
  invalidated_reason: null,
  invalidated_by_name: null,
  invalidated_diff: null,
};

const MATERIAL_KEY = {
  spec_key: 'material',
  label: 'Material',
  data_type: 'enum',
  unit: null,
  allowed_values: [],
  synonyms: {},
  value_labels: { stainless_steel: 'Stainless Steel' },
};

function baseDetail(overrides: Partial<ProductSpecDetail> = {}): ProductSpecDetail {
  return {
    product_id: 'p-1',
    product_code: 'WC100',
    category_code: 'BR-KS',
    searchable: true,
    diagnosis: { reason: 'eligible', class_label: 'Kitchen Sink', brand_hint: 'Sorento', suffix: null },
    spec: {
      values: { material: { value: 'stainless_steel' } },
      provenance: { material: { source: 'human', confidence: 1, evidence: 'manual' } },
      rendered_text: 'A stainless steel basin tap',
      status: 'authored',
      derived_at: '2026-08-01T09:00:00',
    },
    exceptions: [],
    source_text: 'WC100 basin tap',
    verification: VERIFIED,
    values_hash: 'hash-1',
    ...overrides,
  } as ProductSpecDetail;
}

/** The row `SpecTable` would render, in the exact READABLE shape the tab's
 *  own preview must read through (never the raw stored slug). */
const MATERIAL_ROW = {
  specKey: 'material',
  label: 'Material',
  value: 'stainless_steel',
  unit: null,
  dataType: 'enum',
  options: [],
  source: 'human',
  evidence: null,
  unknownKey: false,
  valueLabels: { stainless_steel: 'Stainless Steel' },
};

function mockSpecHook(
  detail: ProductSpecDetail,
  overrides: Partial<ReturnType<typeof useProductSpecTable>> = {},
) {
  useProductSpecTable.mockReturnValue({
    detail,
    rows: [MATERIAL_ROW],
    registry: [MATERIAL_KEY],
    applicableKeys: [],
    otherKeys: [],
    heldKeys: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    verify: vi.fn(),
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

function baseProduct(overrides: Record<string, unknown> = {}) {
  return {
    id: 'p-1',
    product_code: 'WC100',
    product_name: 'Basin Tap',
    list_price: 250,
    price_tag_description: 'Stored template text',
    ...overrides,
  };
}

/** `useDeferredAction` inside `CheckedLine` is real (only the service is mocked),
 * so it needs a live `QueryClient` under it. */
function renderTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProductSpecificationsTab productId="p-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  usePermissions.mockReturnValue({ permissionSet: new Set(['master_data.products.edit']) });
  useProduct.mockReturnValue({ data: baseProduct(), isLoading: false });
});

afterEach(() => cleanup());

function editButton() {
  return screen.getByRole('button', { name: /edit price tag description/i });
}

function descriptionTextarea() {
  return screen.getByLabelText('Price tag description') as HTMLTextAreaElement;
}

describe('Price tag description block on the Specifications tab (AC-S4-10, AC-S2.1, AC-S2.6)', () => {
  it('renders the stored template read-only, below the values table', () => {
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    // "Product description" is no longer on this tab (AC-S2.5) - it moved to
    // Details; Price tag description sits below the values table (SpecTable,
    // stubbed here) and above Reading and search.
    const specTable = screen.getByTestId('spec-table-stub');
    const priceTagLabel = screen.getByText('Price tag description');
    const readingAndSearch = screen.getByText('Reading and search');
    expect(screen.getByText('Stored template text')).toBeInTheDocument();
    expect(
      specTable.compareDocumentPosition(priceTagLabel) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      priceTagLabel.compareDocumentPosition(readingAndSearch) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('shows the empty-state sentence when the product has no stored template yet (AC-S2.6)', () => {
    useProduct.mockReturnValue({ data: baseProduct({ price_tag_description: null }), isLoading: false });
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(
      screen.getByText('Not set, the price tag uses the product description'),
    ).toBeInTheDocument();
  });

  it('Edit turns the box into a prefilled textarea', () => {
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(editButton());

    expect(descriptionTextarea().value).toBe('Stored template text');
    expect(screen.getByRole('button', { name: /^save$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^cancel$/i })).toBeInTheDocument();
  });

  it('Cancel discards the edit without saving', () => {
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(editButton());
    fireEvent.change(descriptionTextarea(), { target: { value: 'Changed but not saved' } });
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    expect(screen.queryByLabelText('Price tag description')).not.toBeInTheDocument();
    expect(screen.getByText('Stored template text')).toBeInTheDocument();
    expect(updateMutateAsync).not.toHaveBeenCalled();
  });

  it('Escape discards the edit the same way Cancel does', () => {
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(editButton());
    fireEvent.change(descriptionTextarea(), { target: { value: 'Changed but not saved' } });
    fireEvent.keyDown(descriptionTextarea(), { key: 'Escape' });

    expect(screen.queryByLabelText('Price tag description')).not.toBeInTheDocument();
    expect(screen.getByText('Stored template text')).toBeInTheDocument();
    expect(updateMutateAsync).not.toHaveBeenCalled();
  });

  it('Save PATCHes price_tag_description through useUpdateProduct and shows the new text', async () => {
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(editButton());
    fireEvent.change(descriptionTextarea(), { target: { value: '{{spec.material}} tap' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    expect(updateMutateAsync).toHaveBeenCalledWith({
      id: 'p-1',
      data: { price_tag_description: '{{spec.material}} tap' },
    });
  });

  it('the Edit action is hidden without master_data.products.edit', () => {
    usePermissions.mockReturnValue({ permissionSet: new Set(['master_data.products.view']) });
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(
      screen.queryByRole('button', { name: /edit price tag description/i }),
    ).not.toBeInTheDocument();
  });
});

describe('Insert field from the Specifications tab (AC-S4-11)', () => {
  it('Insert field opens the dialog and picking Material inserts {{spec.material}} at the caret', () => {
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(editButton());
    fireEvent.click(screen.getByRole('button', { name: /insert field/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole('dialog')).getByText('Material'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^done$/i }));

    expect(descriptionTextarea().value).toContain('{{spec.material}}');
  });

  it('offers only Product and Specs - no Line, Set or part group (a description cannot address a line)', () => {
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(editButton());
    fireEvent.click(screen.getByRole('button', { name: /insert field/i }));

    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText('Product')).toBeInTheDocument();
    expect(dialog.getByText('Specs')).toBeInTheDocument();
    expect(dialog.queryByText('Set')).not.toBeInTheDocument();
    expect(dialog.queryByText('Line')).not.toBeInTheDocument();
  });
});

describe('Live preview - "Prints as:" (AC-S4-12)', () => {
  it("renders the template against THIS product's own spec values, in readable form, no backend call", () => {
    mockSpecHook(baseDetail());
    useProduct.mockReturnValue({
      data: baseProduct({ price_tag_description: '{{spec.material}} tap' }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('Prints as:')).toBeInTheDocument();
    expect(screen.getByText('Stainless Steel tap')).toBeInTheDocument();
  });

  it('updates live off the textarea while editing, before Save', () => {
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(editButton());
    fireEvent.change(descriptionTextarea(), { target: { value: '{{spec.material}} basin' } });

    expect(screen.getByText('Stainless Steel basin')).toBeInTheDocument();
    // Nothing saved yet.
    expect(updateMutateAsync).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// AC-S4-12, from the S11 browser check (21 Sep): the earlier `baseProduct()`
// above already used the REAL API key names (`product_code`/`product_name`/
// `list_price`) - confirmed against `GET /api/v1/master-data/products/{id}`
// on the lane stack and `app/schemas/product.py`'s `ProductResponse` - so
// there were no invented keys to fix in the mock. What WAS synthetic: its
// `product_name` ('Basin Tap') differed from its `product_code` ('WC100').
// Every real product the S11 browser check tried (SRTKS8547,
// SRTWT1212-SS-GM-DIY - confirmed live, both `product_name === product_
// code`) has no separate marketing name, which the earlier "Prints as:"
// test never exercised (its own template was `{{spec.material}} tap`, no
// `{{product.name}}` at all) - the exact blind spot the browser check
// found. `{{product.name}}` blanking for a name-equals-code product is
// `nameOrBlankIfCode` (`lib/dealer-kit/product-block.ts`), pre-existing and
// pre-r10 (S2) - not a defect this block introduces, and not one this test
// suite should assert around; `{{product.code}}` and `{{product.list_
// price}}` are unaffected by it and both need covering, which they were not
// before.
// ---------------------------------------------------------------------------

describe('Live preview against a REAL product shape - S11 browser check (AC-S4-12)', () => {
  it('{{product.code}} and {{product.list_price}} resolve correctly for a real name-equals-code SKU', () => {
    mockSpecHook(baseDetail());
    useProduct.mockReturnValue({
      data: baseProduct({
        product_code: 'SRTKS8547',
        product_name: 'SRTKS8547',
        list_price: 1090,
        price_tag_description: '{{product.code}} - {{product.list_price}}',
      }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('SRTKS8547 - 1,090')).toBeInTheDocument();
  });

  it('{{product.name}} is blank for a real name-equals-code SKU - nameOrBlankIfCode, not a defect', () => {
    mockSpecHook(baseDetail());
    useProduct.mockReturnValue({
      data: baseProduct({
        product_code: 'SRTKS8547',
        product_name: 'SRTKS8547',
        price_tag_description: '[{{product.name}}]',
      }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('[]')).toBeInTheDocument();
  });

  it('{{product.name}} resolves for a real SKU whose name genuinely differs from its code', () => {
    mockSpecHook(baseDetail());
    useProduct.mockReturnValue({
      data: baseProduct({
        product_code: 'SRTKS8547',
        product_name: 'Sorento Kitchen Sink',
        price_tag_description: '{{product.name}}',
      }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('Sorento Kitchen Sink')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// AC-S4-16 (owner test pass, 21 Sep): a multi-line template - the read-only
// box and "Prints as:" must both keep the line breaks, not collapse them
// into one run-on line the way a plain `<p>` renders whitespace by default.
// ---------------------------------------------------------------------------

const TYPE_ROW = {
  specKey: 'product_type',
  label: 'Type',
  value: 'kitchen_tap',
  unit: null,
  dataType: 'enum',
  options: [],
  source: 'human',
  evidence: null,
  unknownKey: false,
  valueLabels: { kitchen_tap: 'Kitchen Tap' },
};
const TYPE_KEY = {
  spec_key: 'product_type',
  label: 'Type',
  data_type: 'enum',
  unit: null,
  allowed_values: [],
  synonyms: {},
  value_labels: { kitchen_tap: 'Kitchen Tap' },
};
const STEEL_GRADE_KEY = {
  spec_key: 'steel_grade',
  label: 'Steel grade',
  data_type: 'text',
  unit: null,
  allowed_values: [],
  synonyms: {},
};

/** Multiple elements can carry the class Tailwind's whitespace utilities
 *  live on; find the one whose RAW (non-normalized) textContent is the
 *  multi-line text under test. */
function boxContaining(needle: string): HTMLElement {
  const matches = screen.getAllByText((_, el) => Boolean(el?.textContent?.includes(needle)));
  // The function matcher above matches every ANCESTOR whose aggregated
  // textContent also contains the needle, not only the leaf `<p>` that
  // actually renders the text - narrow to the leaf.
  const leaf = matches.find((el) => el.tagName === 'P');
  if (!leaf) throw new Error(`no <p> containing "${needle}"`);
  return leaf;
}

describe('Multi-line templates (AC-S4-16)', () => {
  it('the read-only box keeps a 3-line template as 3 lines, not collapsed', () => {
    mockSpecHook(baseDetail(), { rows: [TYPE_ROW], registry: [TYPE_KEY] });
    useProduct.mockReturnValue({
      data: baseProduct({
        product_code: 'CBF3612',
        price_tag_description: '{{product.code}}\n{{spec.product_type}}\nMade in Malaysia',
      }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    const box = boxContaining('{{product.code}}');
    expect(box.className).toMatch(/whitespace-pre-(line|wrap)/);
    expect(box.textContent).toBe(
      '{{product.code}}\n{{spec.product_type}}\nMade in Malaysia',
    );
  });

  it('"Prints as:" resolves the same 3-line template as 3 lines, not collapsed', () => {
    mockSpecHook(baseDetail(), { rows: [TYPE_ROW], registry: [TYPE_KEY] });
    useProduct.mockReturnValue({
      data: baseProduct({
        product_code: 'CBF3612',
        price_tag_description: '{{product.code}}\n{{spec.product_type}}\nMade in Malaysia',
      }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    const box = boxContaining('CBF3612');
    expect(box.className).toMatch(/whitespace-pre-(line|wrap)/);
    expect(box.textContent).toBe('CBF3612\nKitchen Tap\nMade in Malaysia');
  });

  it('Save sends the multi-line text with its newlines intact', async () => {
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(editButton());
    fireEvent.change(descriptionTextarea(), { target: { value: 'Line1\nLine2\nLine3' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    expect(updateMutateAsync).toHaveBeenCalledWith({
      id: 'p-1',
      data: { price_tag_description: 'Line1\nLine2\nLine3' },
    });
  });
});

// ---------------------------------------------------------------------------
// AC-S4-17 (owner test pass, 21 Sep): a line whose ENTIRE content came from
// a token that resolved to nothing is dropped along with its newline - the
// "Prints as:" half of this rule, in the tab. The merge-fields.ts half (the
// rule itself, and its Product/Specs-only scope) is
// `lib/dealer-kit/merge-fields.test.tsx`.
// ---------------------------------------------------------------------------

describe('An all-empty line is dropped, in the tab preview (AC-S4-17)', () => {
  it('a line whose only token has no value on this product is dropped, not left blank', () => {
    mockSpecHook(baseDetail(), { rows: [TYPE_ROW], registry: [TYPE_KEY, STEEL_GRADE_KEY] });
    useProduct.mockReturnValue({
      data: baseProduct({
        product_code: 'CBF3612',
        price_tag_description: '{{product.code}}\n{{spec.steel_grade}}\n{{spec.product_type}}',
      }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    const box = boxContaining('CBF3612');
    expect(box.textContent).toBe('CBF3612\nKitchen Tap');
  });
});

// ---------------------------------------------------------------------------
// AC-S4-18 (owner test pass, 21 Sep): a token naming a field the catalog
// does not offer - `{{spec.type}}` when the real key is `product_type` - is
// named under "Prints as:" instead of silently vanishing. "Known" = the
// SAME restricted catalog Insert field offers
// (`mergeFieldCatalog(specKeys, ['Product', 'Specs'])`).
// ---------------------------------------------------------------------------

describe('An unknown field is named under "Prints as:" (AC-S4-18)', () => {
  it('a single unknown {{spec.*}} token is named', () => {
    mockSpecHook(baseDetail(), { rows: [], registry: [TYPE_KEY, STEEL_GRADE_KEY] });
    useProduct.mockReturnValue({
      data: baseProduct({ price_tag_description: '{{spec.type}}' }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    const warning = screen.getByText('Unknown field: {{spec.type}}');
    expect(warning.className).toMatch(/text-destructive/);
  });

  it('an unknown {{product.*}} token is named too', () => {
    mockSpecHook(baseDetail(), { rows: [], registry: [TYPE_KEY, STEEL_GRADE_KEY] });
    useProduct.mockReturnValue({
      data: baseProduct({ price_tag_description: '{{product.nope}}' }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.getByText('Unknown field: {{product.nope}}')).toBeInTheDocument();
  });

  it('several unknown tokens are listed comma separated, in one line', () => {
    mockSpecHook(baseDetail(), { rows: [], registry: [TYPE_KEY, STEEL_GRADE_KEY] });
    useProduct.mockReturnValue({
      data: baseProduct({ price_tag_description: '{{spec.type}} {{product.nope}}' }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(
      screen.getByText('Unknown field: {{spec.type}}, {{product.nope}}'),
    ).toBeInTheDocument();
  });

  it('a KNOWN field with no value on this product is never flagged unknown', () => {
    mockSpecHook(baseDetail(), { rows: [], registry: [TYPE_KEY, STEEL_GRADE_KEY] });
    useProduct.mockReturnValue({
      data: baseProduct({ price_tag_description: '{{spec.steel_grade}}' }),
      isLoading: false,
    });
    render(<ProductSpecificationsTab productId="p-1" />);

    expect(screen.queryByText(/Unknown field/)).not.toBeInTheDocument();
  });

  it('Save stays enabled with an unknown field in the template', () => {
    mockSpecHook(baseDetail());
    render(<ProductSpecificationsTab productId="p-1" />);

    fireEvent.click(editButton());
    fireEvent.change(descriptionTextarea(), { target: { value: '{{spec.type}}' } });

    expect(screen.getByRole('button', { name: /^save$/i })).not.toBeDisabled();
  });
});

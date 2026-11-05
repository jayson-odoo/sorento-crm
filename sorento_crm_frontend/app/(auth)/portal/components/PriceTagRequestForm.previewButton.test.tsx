/** Owner ruling 3 Nov 14:10: the draft form ends in Approve or Escalate to marketing. */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../lib/price-tag-request-service', async () => {
  const { computeLinePricing } = await import('@/app/(auth)/portal/components/__fixtures__/line-pricing');
  return {
  lookupLinePricing: vi.fn(async (mode: string, lines: unknown[]) =>
    computeLinePricing(mode as 'list' | 'selling', lines as never),
  ),
  lookupDebtors: vi.fn(),
  lookupPromotions: vi.fn(async () => []),
  lookupTagItems: vi.fn(),
  lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  updateRequest: vi.fn(),
  deleteRequest: vi.fn(),
  submitRequest: vi.fn(),
  submitAndEscalate: vi.fn().mockResolvedValue({ status: 'new' }),
  submitAndApprove: vi.fn().mockResolvedValue({ status: 'approved' }),
  lookupTagPreviewForRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
  listReviewComments: vi.fn(async () => []),
  collectRequest: vi.fn(),
  };
});

vi.mock('../lib/portal-client', () => ({
  uploadAttachment: vi.fn(),
  getPriceTagDesign: vi.fn(),
  // D7 r3: PriceTagRequestForm now reads visible_form_types off /me on
  // mount for a NEW request - granted here so these suites (about
  // something else entirely) are unaffected.
  fetchMe: vi.fn().mockResolvedValue({ visible_form_types: ['price_tag_request'] }),
}));

// Native `<select>` stand-in: the real component is a Radix popover whose
// options only exist while open. `id` maps to the field's accessible name the
// same way the existing sibling test files do it (decoupled from the real
// visible `<Label>` text, which is a plain association here, not a lookup).
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange?: (v: string) => void;
    onOptionChange?: (
      o: { value: string; label: string; description?: string } | null,
    ) => void;
    options?: { value: string; label: string; description?: string }[];
    fetchOptions?: (
      q: string,
    ) => Promise<{ value: string; label: string; description?: string }[]>;
    placeholder?: string;
  }) => {
    const [async, setAsync] = React.useState<
      { value: string; label: string; description?: string }[]
    >([]);
    React.useEffect(() => {
      if (props.fetchOptions) void props.fetchOptions('').then(setAsync);
    }, [props.fetchOptions]);
    const options = props.options ?? async;
    const ariaLabel =
      props.id === 'debtor'
        ? 'Customer'
        : props.id === 'promotion'
          ? 'Promotion'
          : (props.placeholder ?? '');
    return (
      <select
        aria-label={ariaLabel}
        value={props.value}
        onChange={(e) => {
          props.onChange?.(e.target.value);
          props.onOptionChange?.(
            options.find((o) => o.value === e.target.value) ?? null,
          );
        }}
      >
        <option value="">{props.placeholder ?? ''}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: { value: string[]; disabled?: boolean }) => (
    <select
      multiple
      aria-label="Alternatives"
      disabled={props.disabled}
      value={props.value}
      onChange={() => {}}
    />
  ),
}));

// The live preview is tested in components/dealer-kit; here it records the props the form hands
// each instance: the whole-request one must be in popup mode, never an inline card.
const previews = vi.hoisted(() => ({ calls: [] as Record<string, unknown>[] }));
vi.mock('@/components/dealer-kit/PriceTagLivePreview', async () => {
  const React = await import('react');
  return {
    PriceTagLivePreview: (props: Record<string, unknown>) => {
      previews.calls.push(props);
      const popup = props.popup as { open: boolean } | undefined;
      React.useEffect(() => {
        (props.onReadyChange as ((s: unknown) => void) | undefined)?.({ missing: [], drawn: true, failed: false });
      }, [props.onReadyChange]);
      if (props.lineKey !== undefined) return <div data-testid="line-preview" />;
      return popup?.open ? <div data-testid="sheet-popup" /> : null;
    },
  };
});

vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: () => null,
}));

import {
  createRequest,
  submitAndApprove,
  submitAndEscalate,
  submitRequest,
  lookupTagPreviewForRequest,
  lookupDebtors,
  lookupPromotions,
  lookupTagItems,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption } from '@/test-utils';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const DEBTORS = [{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }];
const PROMOTIONS = [{ id: 'promo-1', name: 'ZZT August Promo' }];
const ITEMS = [
  {
    kind: 'product' as const,
    id: 'prod-uuid-1',
    code: 'CBF-1234',
    name: 'ZZT Kitchen Sink',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  previews.calls.length = 0;
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupPromotions).mockResolvedValue(PROMOTIONS);
  asMock(lookupTagItems).mockResolvedValue(ITEMS);
  asMock(createRequest).mockResolvedValue({ id: 'req-1' });
});

// Need by is optional since D-P2b (AC-P8b) and is no longer part of what
// Submit needs: Customer + one line + a price mode (which the form always
// carries, defaulting to List) is the whole requirement (AC-P10). Picking
// the customer auto-opens Sales Order & Lines (AC-P3), which is where the
// Item picker and Add line button live.
async function fillMinimalRequiredFields() {
  await selectOption('Customer', 'ZZTD01');
  fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
  await selectOption('Search a set or product...', 'product:prod-uuid-1');
  await pickPrinting();
}

/**
 * r9 D7: `Printing` has no default and Submit refuses without it, so every
 * test that expects a POST has to answer it first. The control lives in
 * "Additional Information", which is collapsed until a price mode is chosen.
 */
async function pickPrinting() {
  // AC-S1-1/S1-2 (r10): the portal no longer asks who prints - `printBy` is a
  // constant 'self' every payload sends, so there is nothing left to click.
  // Callers keep calling this (kept as a no-op) so the rest of each test body
  // reads the same as it always has.
}


beforeEach(() => {
  vi.clearAllMocks();
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupPromotions).mockResolvedValue(PROMOTIONS);
  asMock(lookupTagItems).mockResolvedValue(ITEMS);
  asMock(createRequest).mockResolvedValue({ id: 'req-1' });
});


async function withALine() {
  await selectOption('Customer', 'ZZTD01');
  fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ }));
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
  await selectOption('Search a set or product...', 'product:prod-uuid-1');
}

describe('O2: the whole-request preview is a button, not an always-on card', () => {
  it('has a Preview button beside Lines, disabled until there is a line to draw', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ }));
    expect(screen.getByRole('button', { name: 'Preview' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
    await selectOption('Search a set or product...', 'product:prod-uuid-1');
    expect(screen.getByRole('button', { name: 'Preview' })).toBeEnabled();
  });

  it('draws no inline sheet; the Preview button opens it', async () => {
    render(<PriceTagRequestForm />);
    await withALine();
    expect(screen.queryByTestId('sheet-popup')).toBeNull();
    const whole = previews.calls.filter((c) => c.lineKey === undefined);
    expect(whole.length).toBeGreaterThan(0);
    expect(whole.every((c) => c.popup !== undefined)).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    expect(screen.getByTestId('sheet-popup')).toBeInTheDocument();
  });

  it('Approve still follows the readiness the hidden preview reports', async () => {
    render(<PriceTagRequestForm />);
    await withALine();
    expect(screen.getByRole('button', { name: /^approve$/i })).toBeEnabled();
  });
});

describe('O4: no reason line under the buttons', () => {
  it('shows no approve-blocked paragraph, and Approve keeps the reason as its tooltip', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first
    const approve = screen.getByRole('button', { name: /^approve$/i });
    expect(screen.queryByTestId('approve-blocked')).toBeNull();
    expect(approve).toBeInTheDocument();
  });
});

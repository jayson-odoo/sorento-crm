/**
 * PRICETAG-REQUEST-LAYOUT (owner, mock v1-v3, 10 Nov): Customers first (several), one "Price
 * tags" section that asks ONE choice (upload a file OR type the items) and then shows only that
 * path, Additional information folded, and Preview as the page's one main button: Approve lives
 * only inside the preview popup. Plan: documentation/plans/dealer-kit/PLAN-pricetag-request-layout-10nov.md.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

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
  SearchableMultiSelect: () => null,
}));

vi.mock('@/components/dealer-kit/RequestCustomersSelect');

// The whole-request preview renders its popup's footer, so the popup's Approve is clickable.
vi.mock('@/components/dealer-kit/PriceTagLivePreview', async () => {
  const React = await import('react');
  return {
    PriceTagLivePreview: (props: Record<string, unknown>) => {
      const popup = props.popup as { open: boolean; footer?: React.ReactNode } | undefined;
      React.useEffect(() => {
        (props.onReadyChange as ((s: unknown) => void) | undefined)?.({ missing: [], drawn: true, failed: false });
      }, [props.onReadyChange]);
      if (props.lineKey !== undefined) return null;
      return popup?.open ? <div data-testid="sheet-popup">{popup.footer}</div> : null;
    },
  };
});

vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: () => <div data-testid="so-dropzone" />,
}));

import {
  createRequest,
  getRequest,
  submitAndApprove,
  lookupTagPreviewForRequest,
  lookupDebtors,
  lookupPromotions,
  lookupTagItems,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption } from '@/test-utils';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const DEBTORS = [
  { code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' },
  { code: 'ZZTD02', name: 'ZZT Second Dealer' },
];
const ITEMS = [{ kind: 'product' as const, id: 'prod-uuid-1', code: 'CBF-1234', name: 'ZZT Kitchen Sink' }];

beforeEach(() => {
  vi.clearAllMocks();
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupPromotions).mockResolvedValue([]);
  asMock(lookupTagItems).mockResolvedValue(ITEMS);
  asMock(createRequest).mockResolvedValue({ id: 'req-1', lines: [] });
});

const sectionTitles = () =>
  Array.from(document.querySelectorAll('[data-slot="card"] button[aria-expanded]')).map((b) =>
    (b.textContent ?? '').trim(),
  );

describe('sections: Customers, Price tags, Additional information', () => {
  it('renders exactly three sections in that order', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    const titles = sectionTitles();
    expect(titles).toHaveLength(3);
    expect(titles[0]).toMatch(/^Customers/);
    expect(titles[1]).toMatch(/^Price tags/);
    expect(titles[2]).toMatch(/^Additional information/);
  });

  it('keeps Additional information folded, even once a line exists', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: 'Type the items' }));
    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
    await selectOption('Search a set or product...', 'product:prod-uuid-1');
    expect(screen.queryByLabelText('Notes')).toBeNull();
  });
});

describe('Price tags: one choice, then only that path', () => {
  it('opens on the choice, with the preferred default and no dropzone or Add line yet', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    expect(screen.getByRole('radiogroup')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload a file' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Type the items' })).toBeInTheDocument();
    expect(screen.queryByTestId('so-dropzone')).toBeNull();
    expect(screen.queryByRole('button', { name: /Add line/ })).toBeNull();
  });

  it('Upload a file shows the existing upload and nothing to type into', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: 'Upload a file' }));
    expect(screen.getByTestId('so-dropzone')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add line/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Upload a file' })).toBeNull();
  });

  it('Type the items shows Add line and no upload; the link switches back', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: 'Type the items' }));
    expect(screen.getByRole('button', { name: /Add line/ })).toBeInTheDocument();
    expect(screen.queryByTestId('so-dropzone')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Upload a file instead' }));
    expect(screen.getByTestId('so-dropzone')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add line/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Type the items instead' }));
    expect(screen.getByRole('button', { name: /Add line/ })).toBeInTheDocument();
  });

  it('switching keeps the lines already in', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: 'Type the items' }));
    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
    await selectOption('Search a set or product...', 'product:prod-uuid-1');
    fireEvent.click(screen.getByRole('button', { name: 'Upload a file instead' }));
    expect(screen.getByLabelText('Search a set or product...')).toBeInTheDocument();
  });

  it('a saved draft with a file reopens on the upload path', async () => {
    asMock(getRequest).mockResolvedValue({
      id: 'req-9', doc_number: 'PT-ZZT-0009', debtor_code: 'ZZTD01', debtor_name: 'ZZT Dealer Sdn Bhd',
      needed_by_date: null, notes: null, price_mode: 'list', status: 'new', line_count: 0,
      created_at: '2026-11-10T00:00:00Z', portal_draft_at: '2026-11-10T00:00:00Z', lines: [],
      attachments: [{ id: 'att-1', file_name: 'so.pdf' }],
    });
    render(<PriceTagRequestForm requestId="req-9" />);
    expect(await screen.findByTestId('so-dropzone')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Type the items' })).toBeNull();
  });
});

describe('Preview is the one main button; Approve is inside the popup', () => {
  async function ready() {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: 'Type the items' }));
    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
    await selectOption('Search a set or product...', 'product:prod-uuid-1');
  }

  it('the page has Preview and no Approve', async () => {
    await ready();
    expect(screen.getByRole('button', { name: 'Preview' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^approve$/i })).toBeNull();
  });

  it('Preview with no customer names the problem and opens nothing', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    expect(await screen.findByText('Select the dealer these tags are for.')).toBeInTheDocument();
    expect(screen.queryByTestId('sheet-popup')).toBeNull();
  });

  it('Preview opens the popup; its Approve approves', async () => {
    asMock(createRequest).mockResolvedValue({ id: 'req-1', lines: [] });
    asMock(lookupTagPreviewForRequest).mockResolvedValue({ tags: [], templates: [] });
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    const popup = await screen.findByTestId('sheet-popup');
    expect(within(popup).getByRole('button', { name: 'Back to edit' })).toBeInTheDocument();
    fireEvent.click(within(popup).getByRole('button', { name: /^approve$/i }));
    await waitFor(() => expect(createRequest).toHaveBeenCalled());
  });

  it('Back to edit closes the popup without approving', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    const popup = await screen.findByTestId('sheet-popup');
    fireEvent.click(within(popup).getByRole('button', { name: 'Back to edit' }));
    expect(screen.queryByTestId('sheet-popup')).toBeNull();
    expect(submitAndApprove).not.toHaveBeenCalled();
  });
});

describe('customers: the payload carries the list', () => {
  it('Save Draft sends customers and the first as the debtor pair', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD02');
    fireEvent.click(screen.getByRole('button', { name: 'Save Draft' }));
    await waitFor(() => expect(createRequest).toHaveBeenCalled());
    expect(asMock(createRequest).mock.calls[0][0]).toMatchObject({
      customers: [{ code: 'ZZTD02', name: 'ZZT Second Dealer' }],
      debtor_code: 'ZZTD02',
      debtor_name: 'ZZT Second Dealer',
    });
  });
});

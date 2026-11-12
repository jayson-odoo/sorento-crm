/**
 * PLAN-portal-price-tag-journey-r8, D-P1 (AC-P1, AC-P2, AC-P3, AC-P7, AC-P9).
 * AC-P8's price-mode-specific behaviour (Selling never disabled, Promotion
 * inside Price) is `PriceTagRequestForm.priceMode.test.tsx`'s job; this file
 * owns the section shell itself: order, open/collapse, the three auto-open
 * rules and the collapsed-header summaries.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../lib/price-tag-request-service', () => ({
  lookupDebtors: vi.fn(),
  lookupPromotions: vi.fn(async () => []),
  lookupTagItems: vi.fn(),
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  updateRequest: vi.fn(),
  deleteRequest: vi.fn(),
  submitRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
  listReviewComments: vi.fn(async () => []),
  collectRequest: vi.fn(),
}));

vi.mock('../lib/portal-client', () => ({
  uploadAttachment: vi.fn(),
  getPriceTagDesign: vi.fn(),
  // D7 r3: PriceTagRequestForm now reads visible_form_types off /me on
  // mount for a NEW request - granted here so these suites (about
  // something else entirely) are unaffected.
  fetchMe: vi.fn().mockResolvedValue({ visible_form_types: ['price_tag_request'] }),
}));

// Native `<select>` stand-in - same shape as the sibling suites.
// PRICETAG-REQUEST-LAYOUT: Customers is a multi-select now; its stand-in is a native select
// labelled "Customer" (components/dealer-kit/__mocks__/RequestCustomersSelect.tsx).
vi.mock('@/components/dealer-kit/RequestCustomersSelect');

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
    const ariaLabel = props.id === 'debtor' ? 'Customer' : (props.placeholder ?? '');
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

vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: () => null,
}));

import {
  createRequest,
  lookupDebtors,
  lookupTagItems,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption, chooseTypedItems } from '@/test-utils';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const DEBTORS = [{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }];
const ITEMS = [
  { kind: 'product' as const, id: 'prod-uuid-1', code: 'CBF-1234', name: 'ZZT Kitchen Sink' },
];

beforeEach(() => {
  vi.clearAllMocks();
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupTagItems).mockResolvedValue(ITEMS);
  asMock(createRequest).mockResolvedValue({ id: 'req-1' });
});

/** The four section headers, in document order. */
// PRICETAG-REQUEST-LAYOUT (owner, 10 Nov): three sections - Customers, Price tags (the old
// Price and Sales Order & Lines merged), Additional information (folded).
function sectionHeaders() {
  return screen
    .getAllByRole('button')
    .filter((b) =>
      ['Customers', 'Price tags', 'Additional information'].some((t) =>
        (b.textContent ?? '').startsWith(t),
      ),
    )
    .filter((b) => b.hasAttribute('aria-expanded'));
}

function sectionButton(title: string) {
  return screen.getByRole('button', { name: new RegExp(`^${title}`) });
}

describe('PriceTagRequestForm - sections (AC-P1)', () => {
  it('renders the three sections in order, only Customers open', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const headers = sectionHeaders();
    expect(headers.map((h) => h.getAttribute('aria-expanded'))).toEqual(['true', 'false', 'false']);
    expect(headers[0]).toHaveTextContent('Customers');
    expect(headers[1]).toHaveTextContent('Price tags');
    expect(headers[2]).toHaveTextContent('Additional information');
  });
});

describe('PriceTagRequestForm - section toggling (AC-P2)', () => {
  it('a header tap opens a collapsed section and aria-expanded flips', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const priceTags = sectionButton('Price tags');
    expect(priceTags).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(priceTags);
    expect(priceTags).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(priceTags);
    expect(priceTags).toHaveAttribute('aria-expanded', 'false');
  });

  it('is a real <button>, so Enter/Space toggle it via native HTML semantics', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const priceTags = sectionButton('Price tags');
    expect(priceTags.tagName).toBe('BUTTON');
    expect(priceTags).toHaveAttribute('type', 'button');
  });
});

describe('PriceTagRequestForm - auto-open rules (AC-P3)', () => {
  it('picking a customer opens Price tags automatically; Customers stays open', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');

    expect(sectionButton('Customers')).toHaveAttribute('aria-expanded', 'true');
    expect(sectionButton('Price tags')).toHaveAttribute('aria-expanded', 'true');
    expect(sectionButton('Additional information')).toHaveAttribute('aria-expanded', 'false');
  });

  it('a section the user closed by hand is not reopened by the rule', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    fireEvent.click(sectionButton('Price tags'));
    fireEvent.click(sectionButton('Price tags'));
    expect(sectionButton('Price tags')).toHaveAttribute('aria-expanded', 'false');

    await selectOption('Customer', 'ZZTD01');
    expect(sectionButton('Price tags')).toHaveAttribute('aria-expanded', 'false');
  });

  it('the first line does NOT open Additional information (owner, mock v1: it is secondary)', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    chooseTypedItems();
    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));

    expect(sectionButton('Additional information')).toHaveAttribute('aria-expanded', 'false');
  });
});

describe('PriceTagRequestForm - collapsed-header summaries (AC-P9)', () => {
  it('Customers summary shows the picked name once collapsed', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');

    fireEvent.click(sectionButton('Customers'));

    expect(sectionButton('Customers')).toHaveTextContent('ZZT Dealer Sdn Bhd');
  });

  it('Price tags summary counts the lines and names the chosen default', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    fireEvent.click(screen.getByRole('radio', { name: 'List price' }));
    chooseTypedItems();
    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));

    fireEvent.click(sectionButton('Price tags'));

    expect(sectionButton('Price tags')).toHaveTextContent('1 line, List price');
  });

  it('an empty section shows no summary', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    fireEvent.click(sectionButton('Additional information'));
    fireEvent.click(sectionButton('Additional information'));

    expect(sectionButton('Additional information').textContent).toBe('Additional information');
  });

  it("a fresh form's Price tags header shows no summary until something is in it", async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    expect(sectionButton('Price tags').textContent).toBe('Price tags');
  });
});

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
}));

vi.mock('../lib/portal-client', () => ({
  uploadAttachment: vi.fn(),
  getPriceTagDesign: vi.fn(),
}));

// Native `<select>` stand-in - same shape as the sibling suites.
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
import { selectOption } from '@/test-utils';

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
function sectionHeaders() {
  return screen
    .getAllByRole('button')
    .filter((b) =>
      ['Customer', 'Sales Order', 'Price', 'Additional Information'].some((t) =>
        (b.textContent ?? '').startsWith(t),
      ),
    );
}

function sectionButton(title: string) {
  return screen.getByRole('button', { name: new RegExp(`^${title}`) });
}

describe('PriceTagRequestForm - sections (AC-P1)', () => {
  it('renders the four sections in order, only Customer open', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const headers = sectionHeaders();
    expect(headers.map((h) => h.getAttribute('aria-expanded'))).toEqual([
      'true',
      'false',
      'false',
      'false',
    ]);
    expect(headers[0]).toHaveTextContent('Customer');
    expect(headers[1]).toHaveTextContent('Sales Order & Lines');
    expect(headers[2]).toHaveTextContent('Price');
    expect(headers[3]).toHaveTextContent('Additional Information');
  });
});

describe('PriceTagRequestForm - section toggling (AC-P2)', () => {
  it('a header tap opens a collapsed section and aria-expanded flips', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const salesOrder = sectionButton('Sales Order');
    expect(salesOrder).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(salesOrder);
    expect(salesOrder).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(salesOrder);
    expect(salesOrder).toHaveAttribute('aria-expanded', 'false');
  });

  it('is a real <button>, so Enter/Space toggle it via native HTML semantics (no custom key handler to bypass)', async () => {
    // jsdom does not synthesize a browser's default action for a keydown -
    // firing `keyDown(..., { key: 'Enter' })` at a plain `<button>` does
    // nothing here even though a real browser DOES turn that into a click,
    // natively, for any `<button>`. So the header's OWN commitment is
    // asserted directly: a native `type="button"` element with no
    // `role="button"` override, which is what makes Enter/Space work at
    // all without this component wiring up its own key handler.
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    const salesOrder = sectionButton('Sales Order');
    expect(salesOrder.tagName).toBe('BUTTON');
    expect(salesOrder).toHaveAttribute('type', 'button');

    fireEvent.click(salesOrder);
    expect(salesOrder).toHaveAttribute('aria-expanded', 'true');
  });
});

describe('PriceTagRequestForm - auto-open rules (AC-P3, AC-P7)', () => {
  it('picking a customer opens Sales Order & Lines automatically; Customer stays open', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');

    expect(sectionButton('Customer')).toHaveAttribute('aria-expanded', 'true');
    expect(sectionButton('Sales Order')).toHaveAttribute('aria-expanded', 'true');
  });

  it('a section the user closed by hand is not reopened by the rule', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    // Open it first (so there is something to close), then close it by hand.
    fireEvent.click(sectionButton('Sales Order'));
    fireEvent.click(sectionButton('Sales Order'));
    expect(sectionButton('Sales Order')).toHaveAttribute('aria-expanded', 'false');

    // The rule that would have opened it (picking a customer) must not
    // override the user's own close.
    await selectOption('Customer', 'ZZTD01');
    expect(sectionButton('Sales Order')).toHaveAttribute('aria-expanded', 'false');
  });

  it('the first line landing opens Price automatically', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    expect(sectionButton('Price')).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));

    await waitFor(() =>
      expect(sectionButton('Price')).toHaveAttribute('aria-expanded', 'true'),
    );
  });
});

describe('PriceTagRequestForm - collapsed-header summaries (AC-P9)', () => {
  it('Customer summary shows the picked name once collapsed', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');

    fireEvent.click(sectionButton('Customer'));

    expect(sectionButton('Customer')).toHaveTextContent('ZZT Dealer Sdn Bhd');
  });

  it('Sales Order & Lines summary reads "<n> lines, <m> files" once it holds a line', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Customer', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
    await waitFor(() =>
      expect(sectionButton('Price')).toHaveAttribute('aria-expanded', 'true'),
    );

    fireEvent.click(sectionButton('Sales Order'));

    expect(sectionButton('Sales Order')).toHaveTextContent('1 line, 0 files');
  });

  it('an empty section shows no summary', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    // Additional Information holds nothing yet - opened and closed by hand,
    // since nothing has triggered its auto-open rule.
    fireEvent.click(sectionButton('Additional Information'));
    fireEvent.click(sectionButton('Additional Information'));

    // Only the section title, no summary line appended after it.
    expect(sectionButton('Additional Information').textContent).toBe(
      'Additional Information',
    );
  });

  it("a fresh form's Price header shows no summary until a mode is chosen (review round 2)", async () => {
    // priceMode defaults to 'list' as component STATE, but nobody has
    // CHOSEN it yet on a blank form - the collapsed-header summary must
    // stay empty until a click sets `priceModeChosenRef`, the same rule
    // Additional Information's own summary already follows.
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');

    expect(sectionButton('Price').textContent).toBe('Price');
  });
});

describe('PriceTagRequestForm - price mode auto-open (AC-P8, review round 2)', () => {
  it('choosing List price on a fresh form opens Additional Information, even though List was already the resting default', async () => {
    // The List price button's onClick calls `setPriceMode('list')`
    // unconditionally - on a fresh form priceMode is ALREADY 'list', so
    // React bails out of re-rendering on an unchanged primitive and the
    // auto-open effect (keyed on the `priceMode` dependency) never reruns,
    // even though `priceModeChosenRef.current` was just set to true.
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Customer');
    fireEvent.click(screen.getByRole('button', { name: /^Price/ }));

    fireEvent.click(screen.getByRole('radio', { name: 'List price' }));

    await waitFor(() =>
      expect(sectionButton('Additional Information')).toHaveAttribute(
        'aria-expanded',
        'true',
      ),
    );
  });
});

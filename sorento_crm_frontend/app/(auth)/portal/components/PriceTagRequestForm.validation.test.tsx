/**
 * D48 / AC-M.17 + AC-M.18: a draft saves with nothing in it, and Submit says
 * what is missing instead of posting and hoping.
 *
 * The round this came from: the captain filled the form, pressed Submit, and got
 * a toast reading "Field required" - the pydantic error of a route that was never
 * meant to serve this form. Submit now checks first and reports on the field.
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
  // D7 r3: PriceTagRequestForm now reads visible_form_types off /me on
  // mount for a NEW request - granted here so this suite (about save/submit
  // validation) is unaffected.
  fetchMe: vi.fn().mockResolvedValue({ visible_form_types: ['price_tag_request'] }),
  fetchSubmissionNeighbours: vi.fn().mockResolvedValue({ prev_id: null, next_id: null }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
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
    return (
      <select
        aria-label={props.id === 'debtor' ? 'Debtor' : (props.placeholder ?? '')}
        value={props.value}
        onChange={(e) => {
          props.onChange(e.target.value);
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
    <select multiple aria-label="Alternatives" disabled={props.disabled} value={props.value} onChange={() => {}} />
  ),
}));

// A button that buffers one pending file, standing in for a real drop - the
// dropzone's own drag/paste/upload mechanics are AttachmentDropzone.test.tsx's
// job. This file only needs `pendingFiles` to become non-empty (AC-S1-2).
vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: (props: {
    pendingFiles?: File[];
    onPendingFilesChange?: (files: File[]) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        props.onPendingFilesChange?.([
          ...(props.pendingFiles ?? []),
          new File(['zzt'], 'ZZT-po.pdf', { type: 'application/pdf' }),
        ])
      }
    >
      Attach PO file
    </button>
  ),
}));

import {
  createRequest,
  getRequest,
  lookupDebtors,
  lookupTagItems,
  submitRequest,
  submitAndEscalate,
  updateRequest,
} from '../lib/price-tag-request-service';
import { uploadAttachment } from '../lib/portal-client';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption } from '@/test-utils';

const DEBTORS = [{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }];
const ITEMS = [
  { kind: 'product' as const, id: 'prod-uuid-1', code: 'CBF-1234', name: 'ZZT Kitchen Sink' },
];

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  asMock(lookupDebtors).mockResolvedValue(DEBTORS);
  asMock(lookupTagItems).mockResolvedValue(ITEMS);
  asMock(createRequest).mockResolvedValue({ id: 'req-1' });
  asMock(updateRequest).mockResolvedValue({ id: 'req-1' });
  asMock(submitRequest).mockResolvedValue({ status: 'new' });
});

// The lines table, the "Add line" button and the Sales Order dropzone all
// live inside the "Sales Order & Lines" section (D-P1), collapsed until a
// customer is picked (AC-P3) or opened by hand - Radix's Collapsible
// unmounts its content while closed.
function openSalesOrderSection() {
  fireEvent.click(screen.getByRole('button', { name: /Sales Order & Lines/ }));
}

// Need by and Notes live in "Additional Information" (D-P2b), which auto-
// opens only once a price mode is chosen (AC-P8) - a blank form with no
// price mode chosen has to open it by hand.
function openAdditionalInformationSection() {
  fireEvent.click(
    screen.getByRole('button', { name: /Additional Information/ }),
  );
}

async function addLineWithAProduct() {
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
  await selectOption('Search a set or product...', 'product:prod-uuid-1');
}

/**
 * r9 D7/AC-S3-1: `Printing` has no default and Submit refuses without it, so
 * every test here that expects the POST to happen has to answer it first.
 */
async function pickPrinting() {
  // AC-S1-1/S1-2 (r10): the portal no longer asks who prints - `printBy` is a
  // constant 'self' every payload sends, so there is nothing left to click.
  // Callers keep calling this (kept as a no-op) so the rest of each test body
  // reads the same as it always has.
}

describe('Save Draft validates nothing (D48a)', () => {
  it('saves a form that has one line and no debtor and no date', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openSalesOrderSection();
    await addLineWithAProduct();

    fireEvent.click(screen.getByRole('button', { name: /Save Draft/ }));

    await waitFor(() => expect(createRequest).toHaveBeenCalled());
    const payload = asMock(createRequest).mock.calls[0][0];
    expect(payload.debtor_code).toBeNull();
    expect(payload.debtor_name).toBeNull();
    expect(payload.needed_by_date).toBeNull();
    expect(payload.lines).toHaveLength(1);
  });

  it('saves a form that has a debtor and nothing else', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Debtor', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first

    fireEvent.click(screen.getByRole('button', { name: /Save Draft/ }));

    await waitFor(() => expect(createRequest).toHaveBeenCalled());
    const payload = asMock(createRequest).mock.calls[0][0];
    expect(payload.debtor_code).toBe('ZZTD01');
    expect(payload.lines).toEqual([]);
  });

  it('is disabled only while there is nothing at all to save', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openAdditionalInformationSection();

    expect(screen.getByRole('button', { name: /Save Draft/ })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Notes'), {
      target: { value: 'for the showroom' },
    });

    expect(screen.getByRole('button', { name: /Save Draft/ })).not.toBeDisabled();
  });

  it('a dropped PO file with nothing else filled in still enables Save Draft (AC-S1-2)', async () => {
    // Regression: `hasSomethingToSave` used to check only debtor/promotion/
    // needed-by/notes/lines, so a PO file dropped before anything else was
    // filled in left the button permanently disabled with no way to give the
    // buffered file a draft to upload to.
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openSalesOrderSection();

    expect(screen.getByRole('button', { name: /Save Draft/ })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Attach PO file' }));

    expect(screen.getByRole('button', { name: /Save Draft/ })).not.toBeDisabled();
  });

  it('a retry after create-succeeded-but-flush-failed updates, it does not re-create', async () => {
    // Regression: the created row's id lived only in the `requestId` PROP
    // (the route param), which a retry never gets - Save Draft always looked
    // at `requestId` to decide create-vs-update, so a create that succeeded
    // right before an upload failure was invisible to the next click, and it
    // created a second row.
    asMock(uploadAttachment).mockRejectedValue(new Error('network blip'));

    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openSalesOrderSection();
    fireEvent.click(screen.getByRole('button', { name: 'Attach PO file' }));

    fireEvent.click(screen.getByRole('button', { name: /Save Draft/ }));
    await waitFor(() => expect(createRequest).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(uploadAttachment).toHaveBeenCalledTimes(1));

    // Retry: the same click, now that the draft already exists server-side.
    fireEvent.click(screen.getByRole('button', { name: /Save Draft/ }));
    await waitFor(() => expect(uploadAttachment).toHaveBeenCalledTimes(2));

    expect(createRequest).toHaveBeenCalledTimes(1);
    expect(updateRequest).toHaveBeenCalledTimes(1);
    expect(asMock(updateRequest).mock.calls[0][0]).toBe('req-1');
  });

  // S4 (code review): PARTS_NEED_COMBO and INVALID_PART are both 422s naming
  // `line:<index>` (`price_tag_request_service.py`) - a reopened draft whose
  // product lost its combo, or whose line points at a product this company
  // can no longer see, lands on the row AND toasts "Line N: <message>" so the
  // failure is visible even before the scroll lands. Both codes go through
  // the same `line:<index>` vocabulary, so one case each pins that they map
  // identically.
  it.each([
    ['PARTS_NEED_COMBO', 'This product has no package to add a part to.'],
    ['INVALID_PART', "This line's product could not be found."],
  ])('toasts "Line 1: <message>" on a %s save 422', async (code, message) => {
    asMock(createRequest).mockRejectedValue(
      Object.assign(new Error(message), { code, fields: ['line:0'] }),
    );
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openSalesOrderSection();
    await addLineWithAProduct();

    fireEvent.click(screen.getByRole('button', { name: /Save Draft/ }));

    await waitFor(() => expect(createRequest).toHaveBeenCalled());
    expect(toasts.error).toHaveBeenCalledWith(`Line 1: ${message}`);
    expect(await screen.findByText(message)).toBeInTheDocument();
  });
});

describe('Escalate to marketing says what is missing (D48b; owner ruling 3 Nov)', () => {
  it('is enabled on an empty form and reports instead of posting', async () => {
    // Need by no longer blocks Submit (D-P2b, AC-P8b). r10 AC-S1-3: Printing
    // no longer blocks Submit either - the control (and its refusal) is gone,
    // `print_by` is a constant 'self' - so a blank form has two gaps left:
    // Customer, Lines.
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');

    // Approve waits for a drawn tag; Escalate is the path that checks a blank form.
    expect(screen.getByRole('button', { name: /^approve$/i })).toBeDisabled();
    sendToMarketing();

    expect(
      await screen.findByText('Select the dealer these tags are for.'),
    ).toBeInTheDocument();
    // AC-P10 + crew pass 5 Nov (#2138): EVERY section with a problem opens,
    // not only the first, so the lines error inside "Sales Order & Lines"
    // shows without opening it by hand.
    expect(await screen.findByText('Add at least one line.')).toBeInTheDocument();
    expect(screen.queryByText('Pick the date you need them by.')).toBeNull();
    // AC-S1-3: "Say who prints these tags." must never appear.
    expect(
      screen.queryByText('Say who prints these tags.'),
    ).toBeNull();
    expect(screen.getByTestId('submit-problem-summary')).toHaveTextContent(
      '2 things need attention',
    );
    expect(createRequest).not.toHaveBeenCalled();
  });

  it('names the row that has no item picked', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Debtor', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first
    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));

    sendToMarketing();

    expect(
      await screen.findByText('Pick a set or a product for this line.'),
    ).toBeInTheDocument();
    expect(createRequest).not.toHaveBeenCalled();
  });

  it('clears the error once the field is filled in', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    sendToMarketing();
    await screen.findByText('Select the dealer these tags are for.');

    await selectOption('Debtor', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first

    await waitFor(() =>
      expect(
        screen.queryByText('Select the dealer these tags are for.'),
      ).toBeNull(),
    );
  });

  it('lands a server set-guard refusal on the row it named', async () => {
    asMock(submitAndEscalate).mockRejectedValue(
      Object.assign(
        new Error("Product 'CBF-1234' is classified as 'Bathroom Furniture'."),
        { code: 'SET_GUARD_VIOLATION', fields: ['line:0'] },
      ),
    );
    render(<PriceTagRequestForm />);
    await selectOption('Debtor', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first
    await addLineWithAProduct();
    await pickPrinting();

    sendToMarketing();

    await waitFor(() => expect(submitAndEscalate).toHaveBeenCalled());
    expect(
      await screen.findByText(
        "Product 'CBF-1234' is classified as 'Bathroom Furniture'.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId('submit-problem-summary')).toBeInTheDocument();
  });

  it('lands a server completeness refusal under the field it named', async () => {
    asMock(submitAndEscalate).mockRejectedValue(
      Object.assign(new Error('This request needs a dealer.'), {
        code: 'SUBMIT_INCOMPLETE',
        fields: ['debtor_name'],
      }),
    );
    render(<PriceTagRequestForm />);
    await selectOption('Debtor', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first
    await addLineWithAProduct();
    await pickPrinting();

    sendToMarketing();

    // The form's own wording goes under the field: it says the same thing and
    // says it as a next action. The server sentence is not repeated beside it.
    expect(
      await screen.findByText('Select the dealer these tags are for.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('This request needs a dealer.')).toBeNull();
  });
});


/**
 * Owner ruling 3 Nov: no plain Submit. These tests drive the draft's validation
 * and save path through Escalate to marketing, which runs the same checks as
 * Approve and needs no drawn tag.
 */
function sendToMarketing() {
  // Owner hand test 5 Nov: Escalate checks the form first; the note dialog
  // opens only when nothing is missing.
  if (!screen.queryByLabelText('What marketing needs to fix')) {
    fireEvent.click(screen.getByRole('button', { name: /escalate to marketing/i }));
  }
  if (!screen.queryByLabelText('What marketing needs to fix')) return;
  fireEvent.change(screen.getByLabelText('What marketing needs to fix'), {
    target: { value: 'Please check' },
  });
  fireEvent.click(screen.getByRole('button', { name: /send to marketing/i }));
}


/**
 * Owner hand test 5 Nov (#2138): Escalate to marketing checks the lines FIRST
 * and only then opens a lightbox with the note and Need by. Need by left the
 * form for that dialog.
 */
describe('Escalate to marketing opens a dialog only when the form is complete', () => {
  function clickEscalate() {
    fireEvent.click(screen.getByRole('button', { name: /escalate to marketing/i }));
  }

  it('a missing line is reported on the form and no dialog opens', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Debtor', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first
    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));

    clickEscalate();

    expect(
      await screen.findByText('Pick a set or a product for this line.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByLabelText('What marketing needs to fix')).toBeNull();
    expect(createRequest).not.toHaveBeenCalled();
  });

  it('a complete form opens the Escalate to marketing dialog with the note and Need by', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Debtor', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first
    await addLineWithAProduct();

    clickEscalate();

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Escalate to marketing' })).toBeInTheDocument();
    expect(within(dialog).getByLabelText('What marketing needs to fix')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Need by')).toBeInTheDocument();
    const send = within(dialog).getByRole('button', { name: /send to marketing/i });
    expect(send).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    expect(createRequest).not.toHaveBeenCalled();
  });

  it('Need by is no longer on the form itself', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    openAdditionalInformationSection();

    expect(screen.getByLabelText('Notes')).toBeInTheDocument();
    expect(screen.queryByLabelText('Need by')).toBeNull();
  });

  it('the Need by picked in the dialog (dd/mm/yyyy) is sent with the escalation', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Debtor', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first
    await addLineWithAProduct();
    clickEscalate();
    const dialog = await screen.findByRole('dialog');

    const needBy = within(dialog).getByLabelText('Need by');
    fireEvent.change(needBy, { target: { value: '20/12/2030' } });
    fireEvent.blur(needBy);
    fireEvent.change(within(dialog).getByLabelText('What marketing needs to fix'), {
      target: { value: 'Photo is the old model' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /send to marketing/i }));

    await waitFor(() => expect(submitAndEscalate).toHaveBeenCalledWith('req-1', 'Photo is the old model'));
    expect(asMock(createRequest).mock.calls[0][0].needed_by_date).toBe('2030-12-20');
  });

  it('a draft keeps its Need by and shows it in the dialog', async () => {
    asMock(getRequest).mockResolvedValue({
      id: 'req-1',
      doc_number: 'PT-202611-0001',
      debtor_code: 'ZZTD01',
      debtor_name: 'ZZT Dealer Sdn Bhd',
      needed_by_date: '2030-01-15',
      notes: null,
      price_mode: 'list',
      status: 'draft',
      line_count: 1,
      created_at: '2026-11-01T00:00:00Z',
      portal_draft_at: '2026-11-01T00:00:00Z',
      contact_id: 'contact-1',
      has_completed_export: false,
      lines: [
        {
          id: 'line-1',
          line_type: 'product',
          product_id: 'prod-uuid-1',
          product_set_id: null,
          name: 'ZZT Kitchen Sink',
          code: 'CBF-1234',
          show_promo_price: true,
          quantity: 1,
          alternatives: [],
          included_accessories: null,
        },
      ],
      attachments: [],
    });
    render(<PriceTagRequestForm requestId="req-1" />);
    await waitFor(() => expect(screen.getByLabelText('Debtor')).toHaveValue('ZZTD01'));

    clickEscalate();

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText('Need by')).toHaveValue('15/01/2030');
  });

  it('at 375 px the dialog buttons span its width', async () => {
    render(<PriceTagRequestForm />);
    await selectOption('Debtor', 'ZZTD01');
    fireEvent.click(screen.getByRole('button', { name: /^Sales Order & Lines/ })); // O3: Price opens first
    await addLineWithAProduct();
    clickEscalate();
    const dialog = await screen.findByRole('dialog');

    for (const name of [/send to marketing/i, /cancel/i]) {
      const button = within(dialog).getByRole('button', { name });
      expect(button.className).toMatch(/(^|\s)w-full(\s|$)/);
      expect(button.className).toMatch(/sm:w-auto/);
    }
  });
});

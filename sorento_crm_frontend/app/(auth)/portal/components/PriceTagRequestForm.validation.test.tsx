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
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

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
  lookupDebtors,
  lookupTagItems,
  submitRequest,
  updateRequest,
} from '../lib/price-tag-request-service';
import { uploadAttachment } from '../lib/portal-client';
import { PriceTagRequestForm } from './PriceTagRequestForm';

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

async function addLineWithAProduct() {
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
  await screen.findByText('ZZT Kitchen Sink');
  fireEvent.change(screen.getByLabelText('Search a set or product...'), {
    target: { value: 'product:prod-uuid-1' },
  });
}

describe('Save Draft validates nothing (D48a)', () => {
  it('saves a form that has one line and no debtor and no date', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
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
    await screen.findByLabelText('Debtor');
    fireEvent.change(screen.getByLabelText('Debtor'), {
      target: { value: 'ZZTD01' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Save Draft/ }));

    await waitFor(() => expect(createRequest).toHaveBeenCalled());
    const payload = asMock(createRequest).mock.calls[0][0];
    expect(payload.debtor_code).toBe('ZZTD01');
    expect(payload.lines).toEqual([]);
  });

  it('is disabled only while there is nothing at all to save', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');

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
});

describe('Submit says what is missing (D48b)', () => {
  it('is enabled on an empty form and reports instead of posting', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');

    const submit = screen.getByRole('button', { name: 'Submit' });
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);

    expect(
      await screen.findByText('Select the dealer these tags are for.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Pick the date you need them by.')).toBeInTheDocument();
    expect(screen.getByText('Add at least one line.')).toBeInTheDocument();
    expect(screen.getByTestId('submit-problem-summary')).toHaveTextContent(
      '3 things need attention',
    );
    expect(createRequest).not.toHaveBeenCalled();
  });

  it('names the row that has no item picked', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    fireEvent.change(screen.getByLabelText('Debtor'), {
      target: { value: 'ZZTD01' },
    });
    fireEvent.change(screen.getByLabelText(/Needed by/), {
      target: { value: '2026-09-30' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Add line/ }));

    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    expect(
      await screen.findByText('Pick a set or a product for this line.'),
    ).toBeInTheDocument();
    expect(createRequest).not.toHaveBeenCalled();
  });

  it('clears the error once the field is filled in', async () => {
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await screen.findByText('Select the dealer these tags are for.');

    fireEvent.change(screen.getByLabelText('Debtor'), {
      target: { value: 'ZZTD01' },
    });

    await waitFor(() =>
      expect(
        screen.queryByText('Select the dealer these tags are for.'),
      ).toBeNull(),
    );
  });

  it('lands a server set-guard refusal on the row it named', async () => {
    asMock(submitRequest).mockRejectedValue(
      Object.assign(
        new Error("Product 'CBF-1234' is classified as 'Bathroom Furniture'."),
        { code: 'SET_GUARD_VIOLATION', fields: ['line:0'] },
      ),
    );
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    fireEvent.change(screen.getByLabelText('Debtor'), {
      target: { value: 'ZZTD01' },
    });
    fireEvent.change(screen.getByLabelText(/Needed by/), {
      target: { value: '2026-09-30' },
    });
    await addLineWithAProduct();

    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    await waitFor(() => expect(submitRequest).toHaveBeenCalled());
    expect(
      await screen.findByText(
        "Product 'CBF-1234' is classified as 'Bathroom Furniture'.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId('submit-problem-summary')).toBeInTheDocument();
  });

  it('lands a server completeness refusal under the field it named', async () => {
    asMock(submitRequest).mockRejectedValue(
      Object.assign(new Error('This request needs a dealer.'), {
        code: 'SUBMIT_INCOMPLETE',
        fields: ['debtor_name'],
      }),
    );
    render(<PriceTagRequestForm />);
    await screen.findByLabelText('Debtor');
    fireEvent.change(screen.getByLabelText('Debtor'), {
      target: { value: 'ZZTD01' },
    });
    fireEvent.change(screen.getByLabelText(/Needed by/), {
      target: { value: '2026-09-30' },
    });
    await addLineWithAProduct();

    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    // The form's own wording goes under the field: it says the same thing and
    // says it as a next action. The server sentence is not repeated beside it.
    expect(
      await screen.findByText('Select the dealer these tags are for.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('This request needs a dealer.')).toBeNull();
  });
});

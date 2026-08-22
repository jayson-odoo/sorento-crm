/**
 * ============================================================================
 * CustomerImportDialog - the customer book's import surface.
 * ============================================================================
 * What is pinned here, and why each one matters:
 *
 *  1. TWO PRESSES, NEVER ONE. Test reads the file and writes nothing; only Confirm
 *     queues. `onUpload` must not be called while testing.
 *  2. EVERY COUNT, INCLUDING `unchanged`. A diff showing only changes is
 *     indistinguishable from one that silently failed to read the file.
 *  3. ROW PROBLEMS ARE WARNINGS, NOT A BLOCK. A file with three bad rows out of 900
 *     imports 897, so the skipped rows are acknowledged in a confirm dialog rather
 *     than stopping the import. The confirm dialog's SKIP claim comes from
 *     `summary.would_skip`, never from the warning count: `warnings` also carries
 *     unrecognised columns, unrecognised market segments and the near-name aggregate,
 *     none of which skip anything.
 *  4. AN UNREADABLE FILE STOPS THE IMPORT and names why.
 *  5. UNRECOGNISED COLUMNS ARE NAMED. An unmapped header is the first sign a
 *     client's export changed, and it is a one-row alias fix once someone sees it.
 *  6. THE SHARED FileDropzone is the file surface: a `role="button"` drop-and-click
 *     surface around a hidden, aria-labelled input. Asserted structurally so a
 *     hand-rolled dropzone fails the test.
 *  7. CONFIRM WITHOUT TEST STILL READS FIRST. An unreadable file must not become a
 *     queued job that fails in the background.
 *
 * The service layer is passed in as props and mocked, so no network is involved and
 * the two-press guarantee is asserted on the call log.
 * ============================================================================
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

import { CustomerImportDialog } from './CustomerImportDialog';
import type {
  CustomerImportSummary,
  CustomerImportValidateResult,
} from '../services/customerImportService';

// Every count is a DISTINCT number, so a `getByText` on one can never accidentally
// match another tile.
const SUMMARY: CustomerImportSummary = {
  total_rows: 900,
  would_create: 612,
  would_update: 240,
  would_unchanged: 45,
  would_skip: 3,
  needs_review: 2,
  unmapped_headers: [],
  missing_columns: [],
  problems: [],
};

const CLEAN: CustomerImportValidateResult = {
  valid: true,
  errors: [],
  warnings: [],
  summary: SUMMARY,
};

function xlsx(name = 'debtor-listing.xlsx'): File {
  return new File([new Uint8Array(16)], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

function txt(name = 'notes.txt'): File {
  return new File([new Uint8Array(16)], name, { type: 'text/plain' });
}

function renderDialog(
  over: Partial<React.ComponentProps<typeof CustomerImportDialog>> = {},
) {
  const onOpenChange = vi.fn();
  const onTest = vi.fn().mockResolvedValue(CLEAN);
  const onUpload = vi.fn().mockResolvedValue({
    message: 'Customer import queued.',
    job_id: 'job-1',
    id: 'row-1',
  });
  render(
    <CustomerImportDialog
      open
      onOpenChange={onOpenChange}
      onTest={onTest}
      onUpload={onUpload}
      {...over}
    />,
  );
  return { onOpenChange, onTest, onUpload };
}

function fileInput(): HTMLInputElement {
  return screen.getByLabelText('Customer listing') as HTMLInputElement;
}

function dropSurface(): HTMLElement {
  const surface = fileInput().closest('[role="button"]');
  if (!surface) throw new Error('the file input is not inside a FileDropzone surface');
  return surface as HTMLElement;
}

function choose(file: File) {
  fireEvent.change(fileInput(), { target: { files: [file] } });
}

function button(label: RegExp | string): HTMLElement {
  return screen.getByRole('button', { name: label });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CustomerImportDialog', () => {
  it('opens empty: no counts, and neither action is available without a file', () => {
    renderDialog();

    expect(screen.getByText('Import customers')).toBeInTheDocument();
    expect(button(/^Test/)).toBeDisabled();
    expect(button(/^Confirm/)).toBeDisabled();
    expect(screen.queryByText('New customers')).not.toBeInTheDocument();
  });

  it('takes the file through the shared FileDropzone', () => {
    renderDialog();

    // Structural, so a hand-rolled dropzone fails rather than quietly diverging.
    expect(dropSurface()).toBeInTheDocument();
    expect(fileInput()).toHaveAttribute('accept', '.xlsx,.xls,.xlsm');
    expect(fileInput().className).toContain('hidden');
  });

  it('refuses a wrong extension locally and never sends it', async () => {
    const { onTest } = renderDialog();

    choose(txt());

    expect(button(/^Test/)).toBeDisabled();
    expect(onTest).not.toHaveBeenCalled();
  });

  it('Test reads the file and writes nothing', async () => {
    const { onTest, onUpload } = renderDialog();
    choose(xlsx());

    fireEvent.click(button(/^Test/));

    await waitFor(() => expect(onTest).toHaveBeenCalledTimes(1));
    expect(onUpload).not.toHaveBeenCalled();
  });

  it('shows a loading state while reading', async () => {
    let release: (value: CustomerImportValidateResult) => void = () => {};
    const onTest = vi.fn(
      () => new Promise<CustomerImportValidateResult>((resolve) => (release = resolve)),
    );
    renderDialog({ onTest });
    choose(xlsx());

    fireEvent.click(button(/^Test/));

    await waitFor(() => expect(screen.getByText('Reading the file...')).toBeInTheDocument());
    release(CLEAN);
    await waitFor(() =>
      expect(screen.queryByText('Reading the file...')).not.toBeInTheDocument(),
    );
  });

  it('reports every count, unchanged included', async () => {
    renderDialog();
    choose(xlsx());

    fireEvent.click(button(/^Test/));

    await waitFor(() => expect(screen.getByText('612')).toBeInTheDocument());
    expect(screen.getByText('New customers')).toBeInTheDocument();
    expect(screen.getByText('240')).toBeInTheDocument();
    expect(screen.getByText('45')).toBeInTheDocument();
    expect(screen.getByText('Unchanged')).toBeInTheDocument();
    expect(screen.getByText('Needs a look')).toBeInTheDocument();
  });

  it('names the rows it would skip, with a show-all toggle past the preview limit', async () => {
    const problems = Array.from({ length: 11 }, (_, i) => ({
      row: i + 2,
      reason: 'no customer name',
    }));
    const onTest = vi.fn().mockResolvedValue({
      valid: true,
      errors: [],
      warnings: problems.map((p) => `Row ${p.row}: ${p.reason}`),
      summary: { ...SUMMARY, would_skip: 11, problems },
    });
    renderDialog({ onTest });
    choose(xlsx());

    fireEvent.click(button(/^Test/));

    // The rendering is the shared `ImportFeedbackSections`, which puts the row number in
    // its own element so it can be emphasised - hence the row-scoped assertion rather than
    // one on a single joined string.
    await waitFor(() => expect(screen.getByText('Row 2')).toBeInTheDocument());
    expect(screen.queryByText('Row 12')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Show all 11'));
    expect(screen.getByText('Row 12')).toBeInTheDocument();
    // The skip claim is the summary's own count, never the length of the warning list.
    expect(screen.getByText('11 rows skipped')).toBeInTheDocument();
  });

  it('names unrecognised columns', async () => {
    const onTest = vi.fn().mockResolvedValue({
      ...CLEAN,
      warnings: ['Column not recognised: SALESMAN'],
      summary: { ...SUMMARY, unmapped_headers: ['SALESMAN', 'CREDIT TERM'] },
    });
    renderDialog({ onTest });
    choose(xlsx());

    fireEvent.click(button(/^Test/));

    // One chip per column in the shared rendering: a joined string cannot be read down.
    await waitFor(() => expect(screen.getByText('SALESMAN')).toBeInTheDocument());
    expect(screen.getByText('CREDIT TERM')).toBeInTheDocument();
    expect(screen.getByText(/Columns we did not recognise \(2\)/)).toBeInTheDocument();
  });

  it('a clean file queues straight from Confirm', async () => {
    const { onUpload, onOpenChange } = renderDialog();
    choose(xlsx());

    fireEvent.click(button(/^Confirm/));

    await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(1));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('Confirm reads the file even when Test was never pressed', async () => {
    const { onTest, onUpload } = renderDialog();
    choose(xlsx());

    fireEvent.click(button(/^Confirm/));

    await waitFor(() => expect(onUpload).toHaveBeenCalled());
    expect(onTest).toHaveBeenCalledTimes(1);
  });

  it('an unreadable file blocks the import and says why', async () => {
    const onTest = vi.fn().mockResolvedValue({
      valid: false,
      errors: ['The file has no customer code column.'],
      warnings: [],
      summary: undefined,
    });
    const { onUpload } = renderDialog({ onTest });
    choose(xlsx());

    fireEvent.click(button(/^Confirm/));

    await waitFor(() =>
      expect(screen.getByText('The file has no customer code column.')).toBeInTheDocument(),
    );
    expect(onUpload).not.toHaveBeenCalled();
  });

  it('skipped rows are acknowledged, then the rest of the file still imports', async () => {
    // Three warnings, TWO of them skips: the copy must count the skips off the summary,
    // not off the warning list.
    const onTest = vi.fn().mockResolvedValue({
      valid: true,
      errors: [],
      warnings: [
        'Row 14: no customer name',
        'Row 51: no customer code',
        'Column not recognised: SALESMAN',
      ],
      summary: { ...SUMMARY, would_skip: 2, problems: [{ row: 14, reason: 'no customer name' }] },
    });
    const { onUpload } = renderDialog({ onTest });
    choose(xlsx());

    fireEvent.click(button(/^Confirm/));

    await waitFor(() => expect(screen.getByText('Import anyway?')).toBeInTheDocument());
    expect(onUpload).not.toHaveBeenCalled();
    expect(screen.getByText(/3 warnings/)).toBeInTheDocument();
    expect(screen.getByText(/2 rows will be skipped/)).toBeInTheDocument();

    fireEvent.click(button('Import anyway'));

    await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(1));
  });

  it('a warning that is not a skip never claims a row was skipped', async () => {
    // A clean 900-row file with three unrecognised columns. Nothing is skipped, and the
    // confirm dialog previously read "3 rows need a look. Those rows are skipped" - which
    // was false AND contradicted the panel on the screen behind it.
    const onTest = vi.fn().mockResolvedValue({
      valid: true,
      errors: [],
      warnings: [
        'Column not recognised: SALESMAN',
        'Column not recognised: CREDIT TERM',
        'Market segment not recognised, left unset: RETAIL-X',
      ],
      summary: {
        ...SUMMARY,
        would_skip: 0,
        problems: [],
        unmapped_headers: ['SALESMAN', 'CREDIT TERM'],
      },
    });
    const { onUpload } = renderDialog({ onTest });
    choose(xlsx());

    fireEvent.click(button(/^Confirm/));

    await waitFor(() => expect(screen.getByText('Import anyway?')).toBeInTheDocument());
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('Validation surfaced 3 warnings. Every row still imports.');
    expect(dialog.textContent ?? '').not.toMatch(/skip/i);
    expect(onUpload).not.toHaveBeenCalled();

    fireEvent.click(button('Import anyway'));

    await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(1));
  });

  it('surfaces the backend message when the read fails outright', async () => {
    const onTest = vi
      .fn()
      .mockRejectedValue(new Error('Select a single company before importing customers.'));
    const { onUpload } = renderDialog({ onTest });
    choose(xlsx());

    fireEvent.click(button(/^Test/));

    await waitFor(() =>
      expect(
        screen.getByText('Select a single company before importing customers.'),
      ).toBeInTheDocument(),
    );
    expect(onUpload).not.toHaveBeenCalled();
  });

  it('surfaces a failure to queue', async () => {
    const { toast } = await import('sonner');
    const onUpload = vi.fn().mockRejectedValue(new Error('Queue unavailable'));
    renderDialog({ onUpload });
    choose(xlsx());

    fireEvent.click(button(/^Confirm/));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Queue unavailable'));
  });

  it('offers a shortcut to the queued job', async () => {
    const { toast } = await import('sonner');
    renderDialog();
    choose(xlsx());

    fireEvent.click(button(/^Confirm/));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const calls = vi.mocked(toast.success).mock.calls;
    const [message, options] = calls[calls.length - 1] as unknown as [
      string,
      { action: { label: string; onClick: () => void } },
    ];
    expect(message).toContain('queued');
    options.action.onClick();
    expect(push).toHaveBeenCalledWith('/system-management/import-jobs/job-1');
  });
});

/**
 * "Read a flyer": two sources, one dialog (S5 of PLAN-flyer-read-hardening.md,
 * AC-A7/A9).
 *
 * The shared picker (`LinkAttachmentBrowserDialog`) is mocked to a single
 * button that calls `onConfirm` - it has its own exhaustive test file, and
 * re-rendering its real folder tree + attachment list here would test IT, not
 * this dialog's tab plumbing.
 *
 * CAVEAT (the coder's own note): both `TabsContent` panels use `forceMount`,
 * so both are in the DOM at all times and jsdom does not apply the
 * `data-[state=inactive]:hidden` Tailwind class. Every assertion below reads
 * `data-state`/scopes by testid rather than `toBeVisible()`.
 *
 * Mocks the SERVICE layer (`flyerReadingService`), not the hooks, so the real
 * `useUploadFlyerReading` / `useCreateFlyerReadingFromAttachment` mutations run
 * through actual react-query - matching the convention in
 * `FlyerReadingsList.test.tsx`.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
}));

const { uploadFlyerReading, createFlyerReadingFromAttachment } = vi.hoisted(() => ({
  uploadFlyerReading: vi.fn(),
  createFlyerReadingFromAttachment: vi.fn(),
}));

vi.mock('../../services/flyerReadingService', () => ({
  uploadFlyerReading,
  createFlyerReadingFromAttachment,
  listFlyerReadings: vi.fn(),
  getFlyerReading: vi.fn(),
  seedFromFlyerReading: vi.fn(),
  deleteFlyerReading: vi.fn(),
  applyDimensions: vi.fn(),
}));

// The props the dialog hands the picker, captured so the filter it asks for
// can be pinned: a filter narrower than what the reader accepts makes a real
// flyer invisible in the library and therefore unreachable through the UI.
const { pickerProps } = vi.hoisted(() => ({
  pickerProps: { current: null as Record<string, unknown> | null },
}));

// A single button standing in for the real picker: click it to simulate the
// designer choosing `library-flyer.pdf` and confirming.
vi.mock('@/components/common/LinkAttachmentBrowserDialog', () => ({
  __esModule: true,
  default: (props: { open: boolean; onConfirm?: (s: unknown) => void }) => {
    pickerProps.current = props as unknown as Record<string, unknown>;
    return props.open ? (
      <button
        data-testid="mock-picker-confirm"
        onClick={() => props.onConfirm?.([{ id: 'att-1', name: 'library-flyer.pdf' }])}
      >
        mock-pick
      </button>
    ) : null;
  },
}));

import { UploadFlyerDialog } from './UploadFlyerDialog';

const mockUpload = vi.mocked(uploadFlyerReading);
const mockFromAttachment = vi.mocked(createFlyerReadingFromAttachment);

const READING_BASE = {
  byteSize: 1000,
  codeCount: 5,
  uploadedAt: '2026-08-01T00:00:00',
  headings: [],
  report: {
    matched: [],
    unmatched: [],
    notPromoted: [],
    dimensionCandidates: [],
    duplicates: {},
    promotionId: null,
  },
};

function freshClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function renderDialog() {
  const onOpenChange = vi.fn();
  const utils = render(
    <QueryClientProvider client={freshClient()}>
      <UploadFlyerDialog open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return { ...utils, onOpenChange };
}

function pdfFile(name = 'agency-flyer.pdf') {
  return new File(['%PDF-1.4'], name, { type: 'application/pdf' });
}

/** Radix TabsTrigger activates on mousedown; click alone is not enough in jsdom. */
function selectTab(testId: string) {
  const tab = screen.getByTestId(testId);
  fireEvent.mouseDown(tab, { button: 0 });
  fireEvent.click(tab);
}

beforeEach(() => {
  vi.clearAllMocks();
  pickerProps.current = null;
});

describe('what the picker is asked for', () => {
  it('offers every PDF spelling the reader accepts, and only one file', () => {
    renderDialog();
    selectTab('dk-fr-source-library');
    fireEvent.click(screen.getByTestId('dk-fr-library-browse'));

    // Mirrors PDF_MIME_TYPES in the backend's flyer_reading_service. A shorter
    // list here hides a genuine flyer filed under one of the rarer spellings.
    expect(pickerProps.current?.mimeTypes).toEqual([
      'application/pdf',
      'application/x-pdf',
      'application/acrobat',
      'applications/vnd.pdf',
      'text/pdf',
      'text/x-pdf',
    ]);
    // The backend's "we did not know" leniency is deliberately NOT mirrored:
    // filtering the library on octet-stream would list every binary blob.
    expect(pickerProps.current?.mimeTypes).not.toContain('application/octet-stream');
    expect(pickerProps.current?.maxSelections).toBe(1);
  });
});

describe('the two sources', () => {
  it('renders both tabs with upload as the default', () => {
    renderDialog();

    expect(screen.getByTestId('dk-fr-source-upload')).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('dk-fr-source-library')).toHaveAttribute('data-state', 'inactive');
    expect(document.querySelector('#dk-fr-file')).toBeInTheDocument();
    expect(screen.getByTestId('dk-fr-library-selection')).toHaveTextContent('No file chosen');
  });

  it('preserves both selections across tab switches, submits each to its own mutation, and both land on the review screen', async () => {
    mockUpload.mockResolvedValue({ id: 'r-upload', filename: 'agency-flyer.pdf', pageCount: 3, ...READING_BASE });
    mockFromAttachment.mockResolvedValue({
      id: 'r-lib',
      filename: 'library-flyer.pdf',
      pageCount: 3,
      ...READING_BASE,
    });

    const { onOpenChange } = renderDialog();

    // ---- pick a file in the Upload tab ----------------------------------
    const fileInput = document.querySelector('#dk-fr-file') as HTMLInputElement;
    const file = pdfFile();
    fireEvent.change(fileInput, { target: { files: [file] } });

    // ---- switch to the Library tab and pick there too --------------------
    selectTab('dk-fr-source-library');
    fireEvent.click(screen.getByTestId('dk-fr-library-browse'));
    fireEvent.click(screen.getByTestId('mock-picker-confirm'));
    expect(screen.getByTestId('dk-fr-library-selection')).toHaveTextContent('library-flyer.pdf');

    // ---- back to Upload: the file chosen earlier is still there ----------
    selectTab('dk-fr-source-upload');
    expect((document.querySelector('#dk-fr-file') as HTMLInputElement).files?.[0]?.name).toBe(
      'agency-flyer.pdf',
    );

    // ---- submit from Upload -> the upload mutation, not from-attachment --
    fireEvent.click(screen.getByTestId('dk-fr-upload-submit'));

    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(1));
    expect(mockFromAttachment).not.toHaveBeenCalled();
    await waitFor(() => expect(push).toHaveBeenCalledWith('/dealer-kit/flyer-readings/r-upload'));
    expect(onOpenChange).toHaveBeenCalledWith(false);

    // ---- the Library selection survived the round trip -------------------
    selectTab('dk-fr-source-library');
    expect(screen.getByTestId('dk-fr-library-selection')).toHaveTextContent('library-flyer.pdf');

    // ---- submit from Library -> the from-attachment mutation -------------
    fireEvent.click(screen.getByTestId('dk-fr-upload-submit'));

    await waitFor(() => expect(mockFromAttachment).toHaveBeenCalledTimes(1));
    expect(mockFromAttachment).toHaveBeenCalledWith('att-1', undefined);
    await waitFor(() => expect(push).toHaveBeenCalledWith('/dealer-kit/flyer-readings/r-lib'));
  });
});

describe('errors from either source', () => {
  it('renders the upload failure in dk-fr-upload-error', async () => {
    mockUpload.mockRejectedValue(
      new Error('That flyer is larger than the 50 MB limit. Export it at a lower image quality and upload it again.'),
    );
    renderDialog();

    const fileInput = document.querySelector('#dk-fr-file') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [pdfFile()] } });
    fireEvent.click(screen.getByTestId('dk-fr-upload-submit'));

    const error = await screen.findByTestId('dk-fr-upload-error');
    expect(error).toHaveTextContent('50 MB limit');
  });

  it('renders the from-attachment failure in the same place', async () => {
    mockFromAttachment.mockRejectedValue(new Error('That PDF is password protected.'));
    renderDialog();

    selectTab('dk-fr-source-library');
    fireEvent.click(screen.getByTestId('dk-fr-library-browse'));
    fireEvent.click(screen.getByTestId('mock-picker-confirm'));
    fireEvent.click(screen.getByTestId('dk-fr-upload-submit'));

    const error = await screen.findByTestId('dk-fr-upload-error');
    expect(error).toHaveTextContent('password protected');
  });

  it('clears a prior error when the source is switched', async () => {
    mockUpload.mockRejectedValue(new Error('boom'));
    renderDialog();

    const fileInput = document.querySelector('#dk-fr-file') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [pdfFile()] } });
    fireEvent.click(screen.getByTestId('dk-fr-upload-submit'));
    await screen.findByTestId('dk-fr-upload-error');

    selectTab('dk-fr-source-library');
    expect(screen.queryByTestId('dk-fr-upload-error')).not.toBeInTheDocument();
  });
});

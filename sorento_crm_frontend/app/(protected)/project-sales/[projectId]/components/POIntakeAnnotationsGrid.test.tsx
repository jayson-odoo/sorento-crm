/**
 * P5 follow-up - the DOCUMENT-LEVEL notes card (AC-D4, D11).
 *
 * A note naming a line no longer lives here: it shows inline on that line in
 * `POIntakeLinesGrid`, so a person clears it there and moves straight to the next one. This
 * card is what is left over once a note names no line at all - a signature, a replacement PO
 * for the whole document, a remark. The invariant under test is unchanged for what does land
 * here: a strike-through arrives as a PROPOSAL, the row says what accepting it does, and a
 * rejection is recorded with a reason rather than deleted.
 *
 * The second invariant is the shape: this is the shared DataGrid, keyed on a stable listing
 * key, not a bespoke card grid.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { POAnnotation } from '../../_shared/types/poIntake.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/purchase-orders/v1',
  useSearchParams: () => ({ get: () => null }),
}));

// The shared DataGrid holds its skeleton rows until the column-preferences query settles, and
// under jsdom it never does. The spy doubles as the assertion that the listing key is the
// stable one rather than the pathname, which carries a version id.
const prefsSpy = vi.fn().mockReturnValue({ resetToDefaults: vi.fn(), isLoading: false });
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: (args: unknown) => prefsSpy(args),
}));

import {
  POIntakeAnnotationsGrid,
  PO_INTAKE_ANNOTATIONS_LISTING_KEY,
} from './POIntakeAnnotationsGrid';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

function annotation(overrides: Partial<POAnnotation> = {}): POAnnotation {
  return {
    id: 'a1',
    page_no: 4,
    crop_url: 'https://example.test/crop.png',
    raw_text: 'signed off, superseded by the amendment letter attached',
    written_date: '15/5/26',
    refers_to_lines: [],
    interpretation: 'signature',
    interpretation_json: {},
    state: 'proposed',
    actioned_by_name: null,
    actioned_at: null,
    action_note: null,
    ...overrides,
  };
}

const onAccept = vi.fn(async () => {});
const onEdit = vi.fn(async () => {});
const onReject = vi.fn(async () => {});
const onShowPage = vi.fn();

function renderGrid(
  annotations: POAnnotation[],
  options: { readOnly?: boolean; saving?: string[] } = {},
) {
  return render(
    <POIntakeAnnotationsGrid
      annotations={annotations}
      readOnly={options.readOnly ?? false}
      savingAnnotationIds={options.saving ?? []}
      onShowPage={onShowPage}
      onAccept={onAccept}
      onEdit={onEdit}
      onReject={onReject}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('POIntakeAnnotationsGrid', () => {
  it('says no document-level notes rather than rendering an empty table', () => {
    renderGrid([]);

    expect(screen.getByText('No document-level notes')).toBeInTheDocument();
    expect(
      screen.getByText(/A note naming a line shows on that line instead/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('is one table row per note, not a card', () => {
    renderGrid([
      annotation(),
      annotation({
        id: 'a2',
        interpretation: 'successor_po',
        interpretation_json: { po_number: 'HQ/26/05/087' },
      }),
      annotation({ id: 'a3', interpretation: 'other' }),
    ]);

    // One header row plus one row per note.
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(4);
    expect(
      screen.getByRole('columnheader', { name: /Note/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', { name: /What accepting does/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Reviewed/i })).toBeInTheDocument();
  });

  it('keys column preferences on the listing key, never on a path holding a version id', () => {
    renderGrid([annotation()]);

    expect(PO_INTAKE_ANNOTATIONS_LISTING_KEY).toBe(
      'projects.projects.view::po-annotations',
    );
    expect(prefsSpy).toHaveBeenCalledWith(
      expect.objectContaining({ listingKey: PO_INTAKE_ANNOTATIONS_LISTING_KEY }),
    );
  });

  it('shows the crop and the reading on the row', () => {
    renderGrid([annotation()]);

    expect(screen.getByRole('img', { name: /signed off/i })).toBeInTheDocument();
    expect(screen.getByText('Not reviewed')).toBeInTheDocument();
    expect(screen.getByText('A signature')).toBeInTheDocument();
    expect(screen.getByText('15/5/26')).toBeInTheDocument();
  });

  it('warns a line is still live even when the pencil named none that could be read', () => {
    renderGrid([annotation({ interpretation: 'cancel_line', interpretation_json: {} })]);

    expect(
      screen.getByText('Cancels a line, but the line number was not read.'),
    ).toBeInTheDocument();
    // In the row, in plain sight, not behind a hover.
    expect(
      screen.getByText(/This line is still live until you accept/i),
    ).toBeInTheDocument();
  });

  it('keeps every fact the note carries on its row', () => {
    renderGrid([annotation()]);

    const row = screen.getByRole('img', { name: /signed off/i }).closest('tr');
    expect(row).not.toBeNull();
    const cells = within(row as HTMLElement);
    expect(cells.getByText('Not reviewed')).toBeInTheDocument();
    expect(cells.getByText('A signature')).toBeInTheDocument();
    expect(
      cells.getByText(/signed off, superseded by the amendment letter/),
    ).toBeInTheDocument();
    expect(cells.getByText('15/5/26')).toBeInTheDocument();
    expect(cells.getByRole('button', { name: 'Page 4' })).toBeInTheDocument();
    expect(cells.getByText('Recorded as a signature. No line changes.')).toBeInTheDocument();
  });

  it('truncates the long text with the whole of it on the title', () => {
    renderGrid([annotation()]);

    const written = screen.getByText(/signed off, superseded by the amendment letter/);
    expect(written).toHaveClass('truncate');
    expect(written).toHaveAttribute(
      'title',
      'signed off, superseded by the amendment letter attached',
    );
  });

  it('spells out the effect before accepting, even without a resolvable line', () => {
    renderGrid([annotation({ interpretation: 'cancel_line', interpretation_json: {} })]);

    fireEvent.click(screen.getByRole('button', { name: 'Accept note 1' }));

    const dialogText = screen.getByRole('alertdialog').textContent ?? '';
    expect(dialogText).toMatch(/the line number was not read/);

    fireEvent.click(screen.getByRole('button', { name: /Accept and cancel/i }));
    expect(onAccept).toHaveBeenCalledWith('a1');
  });

  it('names the replacement PO and says the link waits for it', () => {
    renderGrid([
      annotation({
        id: 'a2',
        interpretation: 'successor_po',
        interpretation_json: { po_number: 'HQ/26/05/087' },
      }),
    ]);

    expect(
      screen.getByText(/Records HQ\/26\/05\/087 as the PO that replaces this one/i),
    ).toBeInTheDocument();
    // Not a cancellation, so the row does not warn about a live line.
    expect(screen.queryByText(/still live until you accept/i)).toBeNull();
  });

  it('refuses a rejection with no reason, then records the reason', () => {
    renderGrid([annotation()]);

    fireEvent.click(screen.getByRole('button', { name: 'Reject note 1' }));
    const rejectButton = screen.getByRole('button', { name: /Reject the note/i });
    expect(rejectButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Reason'), {
      target: { value: 'Superseded by the 15/5 amendment' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Reject the note/i }));

    expect(onReject).toHaveBeenCalledWith('a1', 'Superseded by the 15/5 amendment');
  });

  it("sends the human's reading, keeping keys the extractor set", async () => {
    renderGrid([
      annotation({
        interpretation: 'other',
        interpretation_json: { text: 'illegible remark', confidence: 0.4 },
      }),
    ]);

    fireEvent.click(screen.getByRole('button', { name: 'Edit the reading of note 1' }));
    fireEvent.change(screen.getByLabelText('What it says'), {
      target: { value: 'Deliver to site B, not the warehouse' },
    });
    fireEvent.change(screen.getByLabelText('Note'), {
      target: { value: 'Read it on a second pass' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Apply my reading/i }));

    expect(onEdit).toHaveBeenCalledWith('a1', {
      interpretation: 'other',
      interpretation_json: {
        text: 'Deliver to site B, not the warehouse',
        confidence: 0.4,
      },
      note: 'Read it on a second pass',
    });
  });

  it('records a reviewed note with who, when and why, and offers no second action', () => {
    renderGrid([
      annotation({
        state: 'rejected',
        actioned_by_name: 'Yana Abdullah',
        actioned_at: '2026-05-15T02:41:00',
        action_note: 'This is the approval signature, not an amendment.',
      }),
    ]);

    expect(screen.getByText('Rejected')).toBeInTheDocument();
    expect(screen.getByText(/By Yana Abdullah/)).toBeInTheDocument();
    expect(
      screen.getByText('This is the approval signature, not an amendment.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Accept note/ })).toBeNull();
  });

  it('leaves the crop cell empty rather than apologising once per note', () => {
    renderGrid([
      annotation({ crop_url: null }),
      annotation({ id: 'a2', crop_url: null, raw_text: 'confirm 16 nos' }),
    ]);

    expect(screen.queryByText(/No crop/i)).toBeNull();
    expect(screen.queryByRole('img')).toBeNull();
    // The note itself is still fully readable without its crop.
    expect(screen.getByText('confirm 16 nos')).toBeInTheDocument();
  });

  it('offers no write affordance to a reader, but still shows the note', () => {
    renderGrid([annotation()], { readOnly: true });

    expect(screen.getByText('A signature')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Accept note/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Reject note/ })).toBeNull();
  });

  it('holds the actions still while one of them is in flight', () => {
    renderGrid([annotation()], { saving: ['a1'] });

    expect(screen.getByRole('button', { name: 'Accept note 1' })).toBeDisabled();
    expect(
      screen.getByRole('button', { name: 'Edit the reading of note 1' }),
    ).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject note 1' })).toBeDisabled();
  });

  it('lets a row drive the page image from its Page chip', () => {
    renderGrid([annotation()]);

    fireEvent.click(screen.getByRole('button', { name: 'Page 4' }));
    expect(onShowPage).toHaveBeenCalledWith(4);
  });

  it('sends the reader to the paper from the handwriting itself, not only from the page', () => {
    renderGrid([annotation()]);

    // The crop is what a reviewer points at when they ask where this is on the document,
    // so the crop is what takes them there.
    fireEvent.click(
      screen.getByRole('button', { name: 'Show the handwriting on page 4' }),
    );
    expect(onShowPage).toHaveBeenCalledWith(4);

    // The page reference reads as the affordance it is, beside the reading.
    const page = screen.getByRole('button', { name: 'Page 4' });
    expect(page).toHaveAttribute('title', 'Show page 4 of the scan');
    fireEvent.click(page);
    expect(onShowPage).toHaveBeenCalledTimes(2);
    expect(onShowPage).toHaveBeenLastCalledWith(4);
  });

  it('names each action after the note it acts on, so a dozen rows are not a dozen Accepts', () => {
    renderGrid([annotation(), annotation({ id: 'a2' })]);

    fireEvent.click(screen.getByRole('button', { name: 'Accept note 2' }));
    fireEvent.click(screen.getByRole('button', { name: /^Accept$/i }));

    expect(onAccept).toHaveBeenCalledWith('a2');
  });
});

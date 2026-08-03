/**
 * P5 - the handwriting review rows (AC-D4, AC-D6, D11).
 *
 * The invariant under test is that the paper never moves a line on its own: a strike-through
 * arrives as a PROPOSAL, the row says which lines accepting it will change and in what
 * money, and a rejection is recorded with a reason rather than deleted.
 *
 * The second invariant is the shape: this is the shared DataGrid, keyed on a stable listing
 * key, not a bespoke card grid. A document carries a dozen notes and every other list in the
 * product is a table.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { POAnnotation, POVersionLine } from '../../_shared/types/poIntake.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/purchase-orders/v1',
  useSearchParams: () => ({ get: () => null }),
}));

// The shared DataGrid holds its skeleton rows until the column-preferences query settles, and
// under jsdom it never does. The spy doubles as the assertion that the listing key is the
// stable one rather than the pathname, which carries a version id.
const prefsSpy = vi.fn((_args: unknown) => ({ resetToDefaults: vi.fn(), isLoading: false }));
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

function line(overrides: Partial<POVersionLine> = {}): POVersionLine {
  return {
    id: 'l7',
    line_no: 7,
    stock_code_raw: 'SRTFV1001',
    description_raw: 'FLOOR TRAP 100MM',
    qty: '16',
    uom_raw: 'NOS',
    unit_price: '37.50',
    amount: '600.00',
    arithmetic_ok: true,
    is_cancelled: false,
    resolved_product_id: 'prod-9',
    resolved_product_code: 'SRTFV1001',
    resolution_source: 'code',
    page_no: 4,
    ...overrides,
  };
}

function annotation(overrides: Partial<POAnnotation> = {}): POAnnotation {
  return {
    id: 'a1',
    page_no: 4,
    crop_url: 'https://example.test/crop.png',
    raw_text: 'cancel item (7) due to changed the price, refer to new P/O HQ/26/05/087',
    written_date: '15/5/26',
    refers_to_lines: [7],
    interpretation: 'cancel_line',
    interpretation_json: { line_nos: [7] },
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
const onFocusLineNo = vi.fn();

function renderGrid(
  annotations: POAnnotation[],
  options: { readOnly?: boolean; saving?: string[] } = {},
) {
  return render(
    <POIntakeAnnotationsGrid
      annotations={annotations}
      lines={[line()]}
      readOnly={options.readOnly ?? false}
      savingAnnotationIds={options.saving ?? []}
      onShowPage={onShowPage}
      onFocusLineNo={onFocusLineNo}
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
  it('says nothing was found rather than rendering an empty table', () => {
    renderGrid([]);

    expect(screen.getByText(/No handwriting was found on this scan/i)).toBeInTheDocument();
    expect(screen.getByText(/page through the scan on the left/i)).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('is one table row per note, not a card', () => {
    renderGrid([
      annotation(),
      annotation({ id: 'a2', interpretation: 'signature', refers_to_lines: [] }),
      annotation({ id: 'a3', interpretation: 'other', refers_to_lines: [] }),
    ]);

    // One header row plus one row per note.
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(4);
    expect(
      screen.getByRole('columnheader', { name: /What is written/i }),
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

  it('shows the crop, the reading, and what the line still is until it is accepted', () => {
    renderGrid([annotation()]);

    expect(screen.getByRole('img', { name: /cancel item \(7\)/i })).toBeInTheDocument();
    expect(screen.getByText('Not reviewed')).toBeInTheDocument();
    expect(screen.getByText('Cancels a line')).toBeInTheDocument();
    expect(screen.getByText('15/5/26')).toBeInTheDocument();
    // In the row, in plain sight, not behind a hover.
    expect(
      screen.getByText(/This line is still live until you accept/i),
    ).toBeInTheDocument();
  });

  it('keeps every fact the note carries on its row', () => {
    renderGrid([annotation()]);

    const row = screen.getByRole('img', { name: /cancel item \(7\)/i }).closest('tr');
    expect(row).not.toBeNull();
    const cells = within(row as HTMLElement);
    expect(cells.getByText('Not reviewed')).toBeInTheDocument();
    expect(cells.getByText('Cancels a line')).toBeInTheDocument();
    expect(
      cells.getByText(/cancel item \(7\) due to changed the price/),
    ).toBeInTheDocument();
    expect(cells.getByText('15/5/26')).toBeInTheDocument();
    expect(cells.getByRole('button', { name: 'Page 4' })).toBeInTheDocument();
    expect(cells.getByRole('button', { name: 'Line 7' })).toBeInTheDocument();
    expect(
      cells.getByText(/Cancels line 7 \(SRTFV1001, 16 NOS, RM 600\.00\)/),
    ).toBeInTheDocument();
  });

  it('truncates the long text with the whole of it on the title', () => {
    renderGrid([annotation()]);

    const written = screen.getByText(/cancel item \(7\) due to changed the price/);
    expect(written).toHaveClass('truncate');
    expect(written).toHaveAttribute(
      'title',
      'cancel item (7) due to changed the price, refer to new P/O HQ/26/05/087',
    );
  });

  it('spells out the effect in the line and the money before accepting', () => {
    renderGrid([annotation()]);

    fireEvent.click(screen.getByRole('button', { name: 'Accept note 1' }));

    const dialogText = screen.getByRole('alertdialog').textContent ?? '';
    expect(dialogText).toMatch(/line 7 \(SRTFV1001, 16 NOS, RM 600\.00\)/);
    expect(dialogText).toMatch(/stays on the record, marked cancelled/);

    fireEvent.click(screen.getByRole('button', { name: /Accept and cancel/i }));
    expect(onAccept).toHaveBeenCalledWith('a1');
  });

  it('names the replacement PO and says the link waits for it', () => {
    renderGrid([
      annotation({
        id: 'a2',
        interpretation: 'successor_po',
        interpretation_json: { po_number: 'HQ/26/05/087' },
        refers_to_lines: [],
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
        interpretation: 'amend_code',
        interpretation_json: { line_nos: [7], code: 'SRTFV1001', confidence: 0.4 },
      }),
    ]);

    fireEvent.click(screen.getByRole('button', { name: 'Edit the reading of note 1' }));
    fireEvent.change(screen.getByLabelText(/New code/i), {
      target: { value: 'SRTFV1002' },
    });
    fireEvent.change(screen.getByLabelText('Note'), {
      target: { value: 'The pencil reads 1002' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Apply my reading/i }));

    expect(onEdit).toHaveBeenCalledWith('a1', {
      interpretation: 'amend_code',
      interpretation_json: { line_nos: [7], code: 'SRTFV1002', confidence: 0.4 },
      note: 'The pencil reads 1002',
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

    expect(screen.getByText('Cancels a line')).toBeInTheDocument();
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

  it('lets a row drive the page image and the line in focus', () => {
    renderGrid([annotation()]);

    fireEvent.click(screen.getByRole('button', { name: 'Page 4' }));
    expect(onShowPage).toHaveBeenCalledWith(4);

    fireEvent.click(screen.getByRole('button', { name: 'Line 7' }));
    expect(onFocusLineNo).toHaveBeenCalledWith(7);
  });

  it('sends the reader to the paper from the handwriting itself, not only from the page', () => {
    renderGrid([annotation()]);

    // The crop is what a reviewer points at when they ask where this is on the document,
    // so the crop is what takes them there.
    fireEvent.click(
      screen.getByRole('button', { name: 'Show the handwriting on page 4' }),
    );
    expect(onShowPage).toHaveBeenCalledWith(4);

    // The page reference reads as the affordance it is, beside the line chips.
    const page = screen.getByRole('button', { name: 'Page 4' });
    expect(page).toHaveAttribute('title', 'Show page 4 of the scan');
    fireEvent.click(page);
    expect(onShowPage).toHaveBeenCalledTimes(2);
    expect(onShowPage).toHaveBeenLastCalledWith(4);
    // Reaching the page never quietly moves the line in focus.
    expect(onFocusLineNo).not.toHaveBeenCalled();
  });

  it('names each action after the note it acts on, so a dozen rows are not a dozen Accepts', () => {
    renderGrid([annotation(), annotation({ id: 'a2' })]);

    fireEvent.click(screen.getByRole('button', { name: 'Accept note 2' }));
    fireEvent.click(screen.getByRole('button', { name: /Accept and cancel/i }));

    expect(onAccept).toHaveBeenCalledWith('a2');
  });
});

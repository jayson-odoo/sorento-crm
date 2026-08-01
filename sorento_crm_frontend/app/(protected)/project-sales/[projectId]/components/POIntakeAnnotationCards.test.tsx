/**
 * P5 - the handwriting review cards (AC-D4, AC-D6, D11).
 *
 * The invariant under test is that the paper never moves a line on its own: a strike-through
 * arrives as a PROPOSAL, the card says which lines accepting it will change and in what
 * money, and a rejection is recorded with a reason rather than deleted.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { POAnnotation, POVersionLine } from '../../_shared/types/poIntake.types';
import { POIntakeAnnotationCards } from './POIntakeAnnotationCards';

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

function renderCards(
  annotations: POAnnotation[],
  options: { readOnly?: boolean; saving?: string[] } = {},
) {
  return render(
    <POIntakeAnnotationCards
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

describe('POIntakeAnnotationCards', () => {
  it('says nothing was found rather than rendering an empty gap', () => {
    renderCards([]);

    expect(screen.getByText(/No handwriting was found on this scan/i)).toBeInTheDocument();
    expect(screen.getByText(/page through the scan on the left/i)).toBeInTheDocument();
  });

  it('shows the crop, the reading, and what the line still is until it is accepted', () => {
    renderCards([annotation()]);

    expect(screen.getByRole('img', { name: /cancel item \(7\)/i })).toBeInTheDocument();
    expect(screen.getByText('Not reviewed')).toBeInTheDocument();
    expect(screen.getByText('Cancels a line')).toBeInTheDocument();
    expect(screen.getByText(/This line is still live until you accept/i)).toBeInTheDocument();
  });

  it('spells out the effect in the line and the money before accepting', () => {
    renderCards([annotation()]);

    fireEvent.click(screen.getByRole('button', { name: /^Accept$/ }));

    const dialogText = screen.getByRole('alertdialog').textContent ?? '';
    expect(dialogText).toMatch(/line 7 \(SRTFV1001, 16 NOS, RM 600\.00\)/);
    expect(dialogText).toMatch(/stays on the record, marked cancelled/);

    fireEvent.click(screen.getByRole('button', { name: /Accept and cancel/i }));
    expect(onAccept).toHaveBeenCalledWith('a1');
  });

  it('names the replacement PO and says the link waits for it', () => {
    renderCards([
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
    expect(screen.getByText(/link is made when that PO is uploaded/i)).toBeInTheDocument();
  });

  it('refuses a rejection with no reason, then records the reason', () => {
    renderCards([annotation()]);

    fireEvent.click(screen.getByRole('button', { name: /^Reject$/ }));
    const rejectButton = screen.getByRole('button', { name: /Reject the note/i });
    expect(rejectButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Reason'), {
      target: { value: 'Superseded by the 15/5 amendment' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Reject the note/i }));

    expect(onReject).toHaveBeenCalledWith('a1', 'Superseded by the 15/5 amendment');
  });

  it("sends the human's reading, keeping keys the extractor set", async () => {
    renderCards([
      annotation({
        interpretation: 'amend_code',
        interpretation_json: { line_nos: [7], code: 'SRTFV1001', confidence: 0.4 },
      }),
    ]);

    fireEvent.click(screen.getByRole('button', { name: /Edit the reading/i }));
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

  it('records a reviewed card with who, when and why, and offers no second action', () => {
    renderCards([
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
    expect(screen.queryByRole('button', { name: /^Accept$/ })).toBeNull();
  });

  it('says plainly when no crop of the handwriting was captured', () => {
    renderCards([annotation({ crop_url: null })]);

    expect(
      screen.getByText(/No crop of this handwriting was captured/i),
    ).toBeInTheDocument();
  });

  it('offers no write affordance to a reader, but still shows the note', () => {
    renderCards([annotation()], { readOnly: true });

    expect(screen.getByText('Cancels a line')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Accept$/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Reject$/ })).toBeNull();
  });

  it('lets a card drive the page image and the line in focus', () => {
    renderCards([annotation()]);

    fireEvent.click(screen.getByRole('button', { name: 'Page 4' }));
    expect(onShowPage).toHaveBeenCalledWith(4);

    fireEvent.click(screen.getByRole('button', { name: 'Line 7' }));
    expect(onFocusLineNo).toHaveBeenCalledWith(7);
  });
});

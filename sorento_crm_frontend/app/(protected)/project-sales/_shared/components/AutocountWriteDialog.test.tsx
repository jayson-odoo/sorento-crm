/**
 * AC-QTSO-CRM Phase 2 (red): the dialog that shows AutoCount's answer after a write.
 *
 * Plan "Results and refusals" + mock v2 result note: every write is followed by AutoCount's own
 * read-back, so the dialog lists the lines AutoCount holds (not the lines we sent), names every
 * skipped rate-only line and every exploded product set with its components (ruling R6), and
 * lists the changes that wait for AutoCount. A refusal shows the sentence and no lines.
 *
 * Props are this test's proposal: `{ open, onOpenChange, title, result }` with `result` shaped
 * like the route's answer `{outcome, message, doc_no, lines[], warnings[], skipped[],
 * exploded[], waiting[]}`.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { AutocountWriteDialog } from './AutocountWriteDialog';

const DONE = {
  outcome: 'done',
  message: 'QT000777 created in AutoCount',
  doc_no: 'QT000777',
  lines: [
    {
      line_no: 1,
      item_code: 'SRTWB242',
      description: 'Wash basin 242',
      qty: '10',
      unit_price: '180.00',
      location: 'BRW-BB',
      delivery_date: null,
    },
    {
      line_no: 2,
      item_code: 'SRTWC100',
      description: 'Water closet',
      qty: '8',
      unit_price: '950.00',
      location: 'BRW-BB',
      delivery_date: null,
    },
  ],
  warnings: [],
  skipped: [{ code: 'SRTWB250', description: 'Alternate basin' }],
  exploded: [
    {
      code: 'SET-WC01',
      components: [
        { code: 'SRTWC100', qty: '8' },
        { code: 'SRTAV020', qty: '16' },
      ],
    },
  ],
  waiting: [{ verb: 'REMOVE_LINE', line_no: 3, reason: 'Waiting for AutoCount' }],
};

function renderDialog(result: unknown) {
  return render(
    <AutocountWriteDialog
      open
      onOpenChange={vi.fn()}
      title="Create in AutoCount"
      result={result as never}
    />,
  );
}

const text = () => document.body.textContent ?? '';

describe('AutocountWriteDialog', () => {
  it('shows the sentence and the read-back lines AutoCount holds', () => {
    renderDialog(DONE);

    expect(screen.getByText('QT000777 created in AutoCount')).toBeInTheDocument();
    expect(screen.getByText('SRTWB242')).toBeInTheDocument();
    expect(screen.getByText('Wash basin 242')).toBeInTheDocument();
    expect(text()).toContain('BRW-BB');
    expect(text()).toContain('180.00');
  });

  it('names each skipped rate-only line', () => {
    renderDialog(DONE);

    expect(text()).toContain('SRTWB250');
    expect(text()).toContain('Alternate basin');
  });

  it('names each exploded set with its components and quantities', () => {
    renderDialog(DONE);

    expect(text()).toContain('SET-WC01');
    expect(text()).toContain('SRTAV020');
    expect(text()).toContain('16');
  });

  it('lists a change that waits for AutoCount with its reason', () => {
    renderDialog(DONE);

    expect(text()).toContain('Waiting for AutoCount');
    expect(text()).toMatch(/remove/i);
  });

  it('omits the skipped and exploded notes when there are none', () => {
    renderDialog({ ...DONE, skipped: [], exploded: [], waiting: [] });

    expect(text()).not.toContain('SRTWB250');
    expect(text()).not.toContain('SET-WC01');
    expect(text()).not.toContain('Waiting for AutoCount');
  });

  it('shows a refusal as one sentence with no lines', () => {
    renderDialog({
      outcome: 'refused',
      message: 'AutoCount refused: Item code ZZT-X is not in AutoCount. Nothing was changed.',
      doc_no: null,
      lines: [],
      warnings: [],
      skipped: [],
      exploded: [],
      waiting: [],
    });

    expect(
      screen.getByText(
        'AutoCount refused: Item code ZZT-X is not in AutoCount. Nothing was changed.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('SRTWB242')).not.toBeInTheDocument();
  });

  it('shows an unreachable gateway in words', () => {
    renderDialog({
      outcome: 'unreachable',
      message: 'Could not reach AutoCount',
      doc_no: null,
      lines: [],
      warnings: [],
      skipped: [],
      exploded: [],
      waiting: [],
    });

    expect(screen.getByText('Could not reach AutoCount')).toBeInTheDocument();
  });

  it('shows an amber warning beside a done answer', () => {
    renderDialog({
      ...DONE,
      warnings: [{ code: 'QT_ROW_VALUES_INHERITED', message: 'Price and location copied from the quotation' }],
    });

    expect(text()).toContain('Price and location copied from the quotation');
  });
});

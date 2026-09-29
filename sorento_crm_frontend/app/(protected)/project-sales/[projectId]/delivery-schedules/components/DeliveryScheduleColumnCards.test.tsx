/**
 * P6 - the same grid at phone width.
 *
 * A 38-column matrix cannot be read at 375px, and a horizontal scroller there means dragging
 * across two screens to find one number. The unit of work is a COLUMN, so on a phone each column
 * is a card carrying its three totals, and only the open one mounts quantity fields.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { buildColumnStates, groupPhasesByArea } from '../lib/scheduleTotals';
import { DeliveryScheduleColumnCards } from './DeliveryScheduleColumnCards';
import type { ScheduleGridController } from './DeliveryScheduleMatrix';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const phases = [
  {
    id: 'ph1',
    area_group: 'TOWER',
    sequence: 1,
    label: 'Level 2 & 7',
    delivery_date: '2026-07-01',
  },
  {
    id: 'ph2',
    area_group: 'COMMON AREA',
    sequence: 3,
    label: null,
    delivery_date: '2027-06-01',
  },
];

const products = [
  {
    product_id: 'p5',
    product_code: 'SRTFV1001',
    product_name: 'Sensor Urinal Flush Valve',
    customer_code_raw: 'BUI-HB-SRTFV1001',
    resolution_source: 'code' as const,
    reported_total: '16',
    po_qty: '16',
    product_index: 0,
  },
  {
    product_id: null,
    product_code: null,
    product_name: null,
    customer_code_raw: 'BUI-HB-SRTWB7055',
    resolution_source: null,
    reported_total: '927',
    po_qty: null,
    product_index: 1,
  },
];

const cells = [
  { phase_id: 'ph2', product_id: 'p5', product_index: 0, qty: '8' },
  { phase_id: 'ph1', product_id: null, product_index: 1, qty: '927' },
];

function controller(overrides: Partial<ScheduleGridController> = {}): ScheduleGridController {
  const stored = new Map([
    ['ph2|p5', '8'],
    ['ph1|#1', '927'],
  ]);
  return {
    columns: buildColumnStates(products, phases, cells),
    phaseGroups: groupPhasesByArea(phases),
    valueFor: (phaseId, columnKey) => stored.get(`${phaseId}|${columnKey}`) ?? '',
    setDraft: vi.fn(),
    commit: vi.fn(),
    canEdit: true,
    flagActions: {
      canEdit: overrides.canEdit ?? true,
      poOptions: [],
      resolveProduct: vi.fn(),
      fixQuantities: vi.fn(),
      dismissing: false,
    },
    registerColumnRef: vi.fn(),
    focusRequest: null,
    metaFor: () => undefined,
    ...overrides,
  };
}

/**
 * The cards' own open/close toggles. The Flag pill is a popover trigger and carries
 * `aria-expanded` too, so it is told apart by the `aria-haspopup` Radix gives it.
 */
function toggles(): HTMLElement[] {
  return Array.from(
    screen
      .getByTestId('schedule-columns-mobile')
      .querySelectorAll<HTMLElement>('button[aria-expanded]:not([aria-haspopup])'),
  );
}

describe('DeliveryScheduleColumnCards', () => {
  it('gives each column its two numbers and its Flag pill without opening anything', () => {
    render(<DeliveryScheduleColumnCards controller={controller()} />);
    const cards = within(screen.getByTestId('schedule-columns-mobile'));

    expect(cards.getAllByText('Schedule')).toHaveLength(2);
    expect(cards.getAllByText('PO')).toHaveLength(2);
    expect(cards.getByText('Not on the PO')).toBeInTheDocument();
    // The flush valve has ONE thing to fix, the phases not adding up to the sheet's own
    // TOTAL QTY, and one warning: asking for 8 of the 16 ordered is a partial schedule, not a
    // fault. The unmatched column has two: no product, and nothing on the PO to check against.
    expect(cards.getByRole('button', { name: 'Blocks publish, 2 on SRTFV1001' })).toBeInTheDocument();
    expect(
      cards.getByRole('button', { name: 'Blocks publish, 2 on BUI-HB-SRTWB7055' }),
    ).toBeInTheDocument();
    // The customer code is shown whole, never truncated: it is what is read off the paper.
    expect(cards.getByText('BUI-HB-SRTWB7055').className).not.toMatch(/truncate/);
  });

  it('mounts quantity fields only for the column that is open', () => {
    render(<DeliveryScheduleColumnCards controller={controller()} />);
    const cards = within(screen.getByTestId('schedule-columns-mobile'));

    expect(cards.queryByLabelText('Area 3, SRTFV1001')).toBeNull();

    fireEvent.click(toggles()[0]);
    expect(cards.getByLabelText('Area 3, SRTFV1001')).toHaveValue('8');
    // A blank cell stays blank: TOWER does not take this product.
    expect(cards.getByLabelText('Level 2 & 7, SRTFV1001')).toHaveValue('');
  });

  it('opens one card at a time', () => {
    render(<DeliveryScheduleColumnCards controller={controller()} />);
    const cards = within(screen.getByTestId('schedule-columns-mobile'));

    fireEvent.click(toggles()[0]);
    expect(cards.getByLabelText('Area 3, SRTFV1001')).toBeInTheDocument();

    fireEvent.click(toggles()[0]);
    expect(cards.queryByLabelText('Area 3, SRTFV1001')).toBeNull();
  });

  it('locks an unidentified column, and its pill holds the blockers and the picker', async () => {
    render(<DeliveryScheduleColumnCards controller={controller()} />);
    const cards = within(screen.getByTestId('schedule-columns-mobile'));

    fireEvent.click(toggles()[1]);
    expect(cards.getByLabelText('Level 2 & 7, BUI-HB-SRTWB7055')).toBeDisabled();
    // Opening the card shows its quantities, not a stack of findings under it.
    expect(
      screen.queryByText(
        'BUI-HB-SRTWB7055 is not matched to a product. Pick the product this column means.',
      ),
    ).toBeNull();

    fireEvent.click(cards.getByRole('button', { name: /Blocks publish, 2 on BUI-HB-SRTWB7055/ }));
    expect(
      await screen.findByText(
        'BUI-HB-SRTWB7055 is not matched to a product. Pick the product this column means.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Pick the product for BUI-HB-SRTWB7055')).toBeInTheDocument();
  });

  it('lets a wrong-but-resolved column be changed, same as the matrix', async () => {
    render(<DeliveryScheduleColumnCards controller={controller()} />);
    const cards = within(screen.getByTestId('schedule-columns-mobile'));

    // SRTFV1001 is matched already and still does not reconcile. Withholding the picker
    // here left a wrong match unfixable without deleting something.
    fireEvent.click(cards.getByRole('button', { name: /Blocks publish, 2 on SRTFV1001/ }));
    expect(
      await screen.findByLabelText('Change the product for BUI-HB-SRTFV1001'),
    ).toBeInTheDocument();
  });

  it('opens the asked-for card and puts the cursor in its first quantity', async () => {
    // The component checks it is the view on screen before expanding anything, and jsdom
    // lays nothing out, so this is what "the phone is the width being used" looks like.
    const offsetParent = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      'offsetParent',
    );
    Object.defineProperty(HTMLElement.prototype, 'offsetParent', {
      configurable: true,
      get() {
        return document.body;
      },
    });

    try {
      const { rerender } = render(
        <DeliveryScheduleColumnCards controller={controller()} />,
      );
      const cards = within(screen.getByTestId('schedule-columns-mobile'));
      expect(cards.queryByLabelText('Area 3, SRTFV1001')).toBeNull();

      rerender(
        <DeliveryScheduleColumnCards
          controller={controller({ focusRequest: { key: 'p5', nonce: 1 } })}
        />,
      );

      await waitFor(() =>
        expect(cards.getByLabelText('Level 2 & 7, SRTFV1001')).toHaveFocus(),
      );
    } finally {
      if (offsetParent) {
        Object.defineProperty(HTMLElement.prototype, 'offsetParent', offsetParent);
      }
    }
  });

  it('offers no picker and no editing when the user cannot edit', async () => {
    render(<DeliveryScheduleColumnCards controller={controller({ canEdit: false })} />);
    const cards = within(screen.getByTestId('schedule-columns-mobile'));

    fireEvent.click(toggles()[1]);
    fireEvent.click(cards.getByRole('button', { name: /Blocks publish, 2 on BUI/ }));
    await screen.findByTestId('flag-lines');
    expect(screen.queryByLabelText(/Pick the product/i)).toBeNull();
    expect(cards.queryByLabelText(/Change the product/i)).toBeNull();
    expect(cards.getByLabelText('Level 2 & 7, BUI-HB-SRTWB7055')).toBeDisabled();
  });
});

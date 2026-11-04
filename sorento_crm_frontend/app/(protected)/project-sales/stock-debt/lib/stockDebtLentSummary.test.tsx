import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { LentSummary, groupLentBySo } from './stockDebtDemandColumns';

/** OI-RESERVE-USED-ROW crew pass (4 Nov): "Lent to N SOs" counts distinct ORDERS, and its
 *  list opens above the drill grid, inside the screen at 375. */
type Lent = Parameters<typeof groupLentBySo>[0][number];
const lent = (so: string, qty: number): Lent =>
  ({ kind: 'lent', ref: `Lent to ${so} (${qty})`, qty, so_number: so, sales_order_id: `id-${so}` }) as Lent;

// The crew's C-FH16 shape: SO422058 three times plus SO396351.
const CFH16 = [lent('SO422058', 19), lent('SO396351', 72), lent('SO422058', 91), lent('SO422058', 4)];

describe('groupLentBySo', () => {
  it('sums each SO once, first seen first, and rewrites its ref', () => {
    const grouped = groupLentBySo(CFH16);
    expect(grouped.map((entry) => [entry.so_number, entry.qty])).toEqual([
      ['SO422058', 114],
      ['SO396351', 72],
    ]);
    expect(grouped[0].ref).toBe('Lent to SO422058 (114)');
    expect(grouped[1].ref).toBe('Lent to SO396351 (72)');
  });
});

describe('<LentSummary>', () => {
  it('labels distinct SOs and opens its list outside the trigger cell, sized to the screen', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <table>
        <tbody>
          <tr>
            <td data-testid="cell">
              <LentSummary entries={groupLentBySo(CFH16)} />
            </td>
          </tr>
        </tbody>
      </table>,
    );
    const trigger = screen.getByRole('button', { name: /Lent to 2 SOs \(186\)/ });
    await user.click(trigger);
    const popover = await screen.findByTestId('lent-summary-popover');
    // Portalled: not inside the grid cell (where the row's pills drew over it).
    expect(within(screen.getByTestId('cell')).queryByTestId('lent-summary-popover')).toBeNull();
    expect(container.contains(popover)).toBe(false);
    expect(within(popover).getByRole('link', { name: 'SO422058' })).toHaveAttribute(
      'href',
      '/scm/sales-orders/id-SO422058',
    );
    expect(within(popover).getByText('114')).toBeInTheDocument();
    expect(within(popover).getByText('72')).toBeInTheDocument();
    // Never wider than the screen minus its gutters.
    expect(popover.querySelector('div')?.className ?? '').toContain('calc(100vw-2rem)');
  });
});

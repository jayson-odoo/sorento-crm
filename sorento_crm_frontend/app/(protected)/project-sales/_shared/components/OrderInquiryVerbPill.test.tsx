/**
 * S5 (`PLAN-board-oi-mechanical-22sep.md`, AC-B5-1/AC-B5-2, owner's pick, 22 Sep 2026): the
 * State pill reads plain words for what purchasing DOES with a row - To buy / Partly on
 * PO/SPO / On PO/SPO / Done / Cancelled - not the internal verb ("Raised"/"Linked"/
 * "Actioned"/"Partly linked"). Stored values (`raised`/`partly_linked`/`placed`/`actioned`/
 * `cancelled`) are unchanged; only the word a person reads moves, off the ONE map
 * (`STATE_LABEL`) every reader - this pill, the worklist's own State filter, the Lines tab,
 * the board chips (`BoardCellBreakdownDialog` renders this same pill) - has to share.
 */
import { readFileSync } from 'node:fs';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OrderInquiryStatePill, ReservePill, STATE_LABEL } from './OrderInquiryVerbPill';

describe('AC-B5-1: the State pill reads the plain words', () => {
  it('the label map pins the owner’s exact pick for every stored state', () => {
    expect(STATE_LABEL).toEqual({
      raised: 'To buy',
      partly_linked: 'Partly on PO/SPO',
      placed: 'On PO/SPO',
      actioned: 'Done',
      cancelled: 'Cancelled',
    });
  });

  it.each([
    ['raised', 'To buy'],
    ['partly_linked', 'Partly on PO/SPO'],
    ['placed', 'On PO/SPO'],
    ['actioned', 'Done'],
    ['cancelled', 'Cancelled'],
  ])('renders %s as "%s"', (state, label) => {
    render(<OrderInquiryStatePill state={state} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

/**
 * AC-B5-2: no second spelling of the state word anywhere. A blind `grep -rn "'Raised'"`
 * across `app/` (run before writing this test) turns up exactly two hits, NEITHER of which
 * is this pill's own vocabulary:
 *
 *   - `[projectId]/components/CriticalPanel.tsx:59` - `project.is_critical ? 'Raised' :
 *     'Not raised'`, a project's own "critical flag" toggle - an unrelated feature.
 *   - `order-inquiries/[id]/components/OrderInquiryGeneralTab.tsx:34` - the OI HEADER's own
 *     raise-HISTORY timeline ("Raised" vs "Reconfirmed", `entry.kind === 'raised'`) - an
 *     EVENT name, not the per-row state word `STATE_LABEL` answers.
 *
 * `'Actioned'`/`'Linked'`/`'Partly linked'` (the RETIRED spellings) turn up far more widely
 * still (attachments, respond-outbox, reorder's own qty ledger, onboarding chips, upload
 * activity) - none of them this screen's vocabulary either. A blind zero-hits assertion
 * would therefore be red for reasons that have nothing to do with this AC, so this pins the
 * ONE file that is allowed to spell any of the five words at all - the map itself - and
 * fails the moment a SECOND file in the order-inquiry / fulfilment-planning surface defines
 * its own copy of the map instead of importing `STATE_LABEL`.
 */
describe('AC-B5-2: no second spelling of the state word - one map, everywhere it is read', () => {
  it('OrderInquiryClient.tsx reads the shared STATE_LABEL rather than its own copy', () => {
    // Phase 1 (`cfa9dfb9c`) fixed the one duplicate spelling found here (`STATE_OPTIONS`
    // used to say `placed: 'Placed'` where the pill already said `Linked`) - pinned so a
    // later edit cannot reintroduce a second, looser spelling.
    const source = readFileSync(
      require.resolve(
        '../../[projectId]/order-inquiries/components/OrderInquiryClient.tsx',
      ),
      'utf8',
    );
    expect(source).toContain('STATE_LABEL[value]');
    expect(source).not.toMatch(/value:\s*'placed',\s*label:\s*'Placed'/);
    expect(source).not.toMatch(/value:\s*'raised',\s*label:\s*'Raised'/);
  });

  it('every other screen that names a row’s state renders it through OrderInquiryStatePill, not a hand-spelled badge', () => {
    // The worklist's own grid (`orderInquiryWorklistColumns.tsx`) carries no State column
    // at all - only the VERB pill (`OrderInquiryVerbPill`, a different map, ORDER/ADVANCE/
    // ...) - so it is not one of this map's readers and is deliberately not checked here.
    const files = [
      // Lines tab (AC-B3-1's own State column).
      '../../order-inquiries/[id]/components/orderInquiryHeaderLinesColumns.tsx',
      // SCM sales-order detail's "Order inquiry" cell.
      '../../../scm/sales-orders/[id]/components/SalesOrderDetail.tsx',
      // The board's own cell-breakdown dialog - "the board chips" the plan names.
      '../../fulfilment-planning/components/BoardCellBreakdownDialog.tsx',
    ];
    for (const relative of files) {
      const source = readFileSync(require.resolve(relative), 'utf8');
      expect(source).toContain('OrderInquiryStatePill');
    }
  });
});

/**
 * Round 4 (`PLAN-oi-request-cs-reserve.md` section 6e.2, owner round 4, 24 Sep):
 * "The pill is no longer a button" - `ReservePill` is plain text everywhere now, and
 * the two fix-round-2 suites this file used to carry here (the interactive button's
 * own hover/focus affordance classes, and `onClick` receiving the click event) are
 * retired with the button itself. AC-RS-83 (`orderInquiryHeaderLinesColumns.test.tsx`)
 * covers the replacement `reserve_actions` icon-button column instead.
 */
describe('AC-RS-83 (round 4): ReservePill is plain text, never a role=button', () => {
  it('prints the requested qty and carries no button role', () => {
    render(<ReservePill reserveState="requested" requestedQty="107" />);

    expect(screen.getByText('Request to reserve 107')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('prints the reserved qty and carries no button role', () => {
    render(<ReservePill reserveState="reserved" reservedQty="3" />);

    expect(screen.getByText(/reserved 3/i)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

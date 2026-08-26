/**
 * The two books purchasing feeds from the Order Inquiries page (AC-H12/AC-H13),
 * `PLAN-scm-oi-handshake.md`. The dialogs are stubbed to sentinels - what they render is
 * their own suites' subject (`UploadDataMenu.test.tsx` is the sibling test this one
 * mirrors); what belongs here is which entry opens which dialog with which `kind`, that
 * only one opens at a time, and that `onQueued` reaches the caller - the seam the page
 * uses to offer Link now and Open purchase orders.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}

vi.mock('../../../scm/reorder/components/OutstandingUploadDialog', () => ({
  OutstandingUploadDialog: ({
    open,
    kind,
    onQueued,
  }: {
    open: boolean;
    kind: string;
    onQueued?: () => void;
  }) =>
    open ? (
      <div>
        {`outstanding:${kind}`}
        <button type="button" onClick={() => onQueued?.()}>
          finish outstanding upload
        </button>
      </div>
    ) : null,
}));
vi.mock('../../../scm/reorder/components/HistoryUploadDialog', () => ({
  HistoryUploadDialog: ({
    open,
    kind,
    onQueued,
  }: {
    open: boolean;
    kind: string;
    onQueued?: () => void;
  }) =>
    open ? (
      <div>
        {`history:${kind}`}
        <button type="button" onClick={() => onQueued?.()}>
          finish history upload
        </button>
      </div>
    ) : null,
}));

import { OrderInquiryUploadMenu } from './OrderInquiryUploadMenu';

function openMenu(onQueued?: () => void) {
  const result = render(<OrderInquiryUploadMenu onQueued={onQueued} />);
  // Radix opens its menu on pointerdown, which `fireEvent.click` does not synthesise.
  fireEvent.pointerDown(screen.getByRole('button', { name: /^upload$/i }), {
    button: 0,
    ctrlKey: false,
  });
  return result;
}

async function pick(label: RegExp) {
  const item = await screen.findByRole('menuitem', { name: label });
  fireEvent.keyDown(item, { key: 'Enter' });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('OrderInquiryUploadMenu', () => {
  it('offers exactly the two books purchasing feeds, never the sales-order one', async () => {
    openMenu();

    expect(
      await screen.findByRole('menuitem', { name: /Upload purchase orders/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('menuitem', { name: /Upload purchase history/i }),
    ).toBeInTheDocument();
    // CS's document, deliberately absent (plan section 7).
    expect(screen.queryByRole('menuitem', { name: /sales order/i })).toBeNull();
  });

  it('opens no dialog until an entry is chosen', () => {
    openMenu();

    expect(screen.queryByText(/^outstanding:/)).toBeNull();
    expect(screen.queryByText(/^history:/)).toBeNull();
  });

  it('"Upload purchase orders" opens the outstanding dialog with kind=purchase-orders', async () => {
    openMenu();
    await pick(/Upload purchase orders/i);

    expect(await screen.findByText('outstanding:purchase-orders')).toBeInTheDocument();
    expect(screen.queryByText(/^history:/)).toBeNull();
  });

  it('"Upload purchase history" opens the SAME dialog the reorder page calls that', async () => {
    openMenu();
    await pick(/Upload purchase history/i);

    expect(await screen.findByText('history:purchase-history')).toBeInTheDocument();
    expect(screen.queryByText(/^outstanding:/)).toBeNull();
  });

  it('switching entries replaces the open dialog rather than stacking a second one', async () => {
    openMenu();
    await pick(/Upload purchase orders/i);
    expect(await screen.findByText('outstanding:purchase-orders')).toBeInTheDocument();

    fireEvent.pointerDown(screen.getByRole('button', { name: /^upload$/i }), {
      button: 0,
      ctrlKey: false,
    });
    await pick(/Upload purchase history/i);

    expect(await screen.findByText('history:purchase-history')).toBeInTheDocument();
    expect(screen.queryByText('outstanding:purchase-orders')).toBeNull();
    expect(screen.queryAllByText(/^(outstanding|history):/)).toHaveLength(1);
  });

  it('reports onQueued to the caller when the outstanding upload finishes', async () => {
    const onQueued = vi.fn();
    openMenu(onQueued);
    await pick(/Upload purchase orders/i);
    fireEvent.click(await screen.findByRole('button', { name: /finish outstanding upload/i }));

    expect(onQueued).toHaveBeenCalledTimes(1);
  });

  it('reports onQueued to the caller when the purchase-history upload finishes', async () => {
    const onQueued = vi.fn();
    openMenu(onQueued);
    await pick(/Upload purchase history/i);
    fireEvent.click(await screen.findByRole('button', { name: /finish history upload/i }));

    expect(onQueued).toHaveBeenCalledTimes(1);
  });
});

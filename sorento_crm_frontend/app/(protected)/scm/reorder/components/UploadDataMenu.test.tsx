/**
 * The menu that routes each file to the dialog that understands it.
 *
 * The risk this covers is a mis-route: an order book sent to the history importer would be
 * written closed and fully received, and would then be invisible to the plan it was uploaded
 * to feed. So every entry is checked to open the RIGHT dialog with the RIGHT kind.
 *
 * The dialogs are stubbed to sentinels - what they render is their own suites' subject.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

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

vi.mock('./OutstandingUploadDialog', () => ({
  OutstandingUploadDialog: ({ open, kind }: { open: boolean; kind: string }) =>
    open ? <div>{`outstanding:${kind}`}</div> : null,
}));
vi.mock('./HistoryUploadDialog', () => ({
  HistoryUploadDialog: ({ open, kind }: { open: boolean; kind: string }) =>
    open ? <div>{`history:${kind}`}</div> : null,
}));

import { UploadDataMenu } from './UploadDataMenu';

function openMenu() {
  render(<UploadDataMenu />);
  // Keyboard rather than a click: Radix opens the menu on `pointerdown`, which jsdom does
  // not synthesise from `fireEvent.click`. Enter on the trigger is the same code path a
  // keyboard user takes, and it works in both.
  fireEvent.keyDown(screen.getByRole('button', { name: /Upload data/i }), { key: 'Enter' });
}

async function pick(label: RegExp) {
  const item = await screen.findByRole('menuitem', { name: label });
  // Radix menu items respond to keyboard selection in jsdom, where a synthetic click on the
  // item does not always fire `onSelect`.
  fireEvent.keyDown(item, { key: 'Enter' });
}

describe('UploadDataMenu - every channel is reachable', () => {
  it('offers all four files, grouped by what they do to the plan', async () => {
    openMenu();

    // The order book: what the plan is computed from. Neither entry says "outstanding" -
    // each file carries the WHOLE book, and the two list toolbars and the dialog title all
    // word this one action the same way.
    expect(await screen.findByRole('menuitem', { name: /Upload sales orders/i }))
      .toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Upload purchase orders/i }))
      .toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /Outstanding/i })).toBeNull();
    // History and linkage: what the order book does not carry.
    expect(screen.getByRole('menuitem', { name: /Purchase history/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Order inquiry sheet/i })).toBeInTheDocument();
  });

  it('opens no dialog until a file type is chosen', () => {
    openMenu();

    expect(screen.queryByText(/^outstanding:/)).toBeNull();
    expect(screen.queryByText(/^history:/)).toBeNull();
  });
});

describe('UploadDataMenu - each entry routes to the importer that understands the file', () => {
  const cases: ReadonlyArray<readonly [RegExp, string]> = [
    [/Upload sales orders/i, 'outstanding:sales-orders'],
    [/Upload purchase orders/i, 'outstanding:purchase-orders'],
    [/Purchase history/i, 'history:purchase-history'],
    [/Order inquiry sheet/i, 'history:order-inquiry'],
  ];

  for (const [label, expected] of cases) {
    it(`${expected}`, async () => {
      openMenu();
      await pick(label);

      await waitFor(() => expect(screen.getByText(expected)).toBeInTheDocument());
      // Exactly one: two dialogs open at once would each hold their own file.
      expect(screen.queryAllByText(/^(outstanding|history):/)).toHaveLength(1);
    });
  }
});

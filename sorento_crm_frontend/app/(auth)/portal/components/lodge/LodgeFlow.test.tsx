/**
 * S3 Phase 2 - the lodge flow, on both backends.
 *
 * The interesting assertions are the ones that only the wiring can get wrong. The flow's
 * shape was settled in Phase 1 by walking it; what these cover is the seam between the
 * screens and the API:
 *
 * 1. **The tiles survive a failed fetch.** The chooser is the only way an unresolved line
 *    gets a Kind, and roughly a quarter of receipts print nothing usable. An empty grid is
 *    a dead end for the consumer, so a failed `kinds()` must leave the seeded list standing
 *    rather than render nothing.
 *
 * 2. **A correction re-runs the dealer match.** The whole point of pre-filling an EDITABLE
 *    form is that fixing a misread shop name changes the ANSWER. Without the re-check, the
 *    correction changes what is on screen and nothing else, and the ledger still records
 *    the wrong dealer - which is the exact failure the resolved/candidate split exists to
 *    prevent.
 *
 * 3. **A refused submission is visible.** The one refusal the backend issues is consent. A
 *    consumer who thinks the form silently failed submits again, so a swallowed error turns
 *    one lodgement into several.
 *
 * 4. **The verdict summary never reads worse than the truth.** It is the value exchanged
 *    for the data, and the engine answers per part.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { LodgeFlow } from './LodgeFlow';
import { MOCK_KINDS } from './lodgeMocks';
import type { LodgeBackend } from './lodgeBackend';

const recheckDealer = vi.fn();

vi.mock('./lodgeBackend', async () => {
  const actual = await vi.importActual<typeof import('./lodgeBackend')>('./lodgeBackend');
  return {
    ...actual,
    // The factory must not close over a top-level const declared after it, or the real
    // module silently stays in place and the spy never fires.
    recheckDealer: (...args: unknown[]) => recheckDealer(...args),
  };
});

function backend(overrides: Partial<LodgeBackend> = {}): LodgeBackend {
  return {
    kinds: async () => MOCK_KINDS,
    extract: async () => ({
      shop_name_raw: 'TOTAL HOME DIY SDN BHD',
      dealer: { state: 'resolved', customer_name: 'TOTAL HOME DIY SDN BHD' },
      purchase_date: '2025-10-16',
      document_number: 'KCS-2112-0054',
      sorento_order_number: null,
      lines: [
        {
          claimed_text: 'SRTWC8152 WATER CLOSET',
          model_code_raw: 'SRTWC8152',
          kind_code: 'water_closet',
          kind_label: 'Water Closet',
          product_id: null,
          quantity: 1,
        },
      ],
    }),
    submit: async () => ({
      complaint_number: 'CMP2026-0148',
      warranty: { state: 'covered', summary: 'Covered by warranty until 2030-10-16.' },
    }),
    ...overrides,
  };
}

/**
 * Photo, then continue - the flow will not leave step 1 without one.
 *
 * On the LIVE route the photo has to be a real File, because the files ARE what gets sent
 * to extraction. On the mock route there is nothing to send, so a tap just counts one.
 */
async function reachConfirm({ live = false }: { live?: boolean } = {}) {
  if (live) {
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['receipt'], 'receipt.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [file] } });
  } else {
    fireEvent.click(screen.getByRole('button', { name: /add a photo/i }));
  }
  fireEvent.click(screen.getByRole('button', { name: /continue/i }));
  await waitFor(() => expect(screen.getByText(/did we get this right/i)).toBeInTheDocument());
}

/**
 * The confirm step's button reads "Yes, that is right" when extraction produced something
 * and "Continue" when it did not - the copy fix from walking the `unmatched` scenario, where
 * asking a consumer to confirm an empty sentence read as a broken screen.
 */
async function reachKind() {
  await reachConfirm();
  fireEvent.click(screen.getByRole('button', { name: /yes, that is right|continue/i }));
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Water Closet' })).toBeInTheDocument(),
  );
}

async function reachSubmit() {
  await reachKind();
  fireEvent.click(screen.getByRole('button', { name: 'Water Closet' }));
  fireEvent.click(screen.getByRole('button', { name: /^continue$/i }));
  // Step 4 (fault + photos) then step 5 (site). Neither gates on content: a consumer who
  // cannot describe the fault must still be able to send the report (AC-C14).
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument(),
  );
  fireEvent.click(screen.getByRole('button', { name: /^continue$/i }));
  await waitFor(() => expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument());
}

describe('LodgeFlow', () => {
  it('keeps the tiled chooser usable when the kinds fetch fails', async () => {
    render(
      <LodgeFlow
        backend={backend({
          kinds: async () => {
            throw new Error('offline');
          },
        })}
      />,
    );
    // The seeded list stands. An empty grid would leave a consumer with nothing to click
    // on the one screen that resolves what the receipt could not.
    await reachKind();
  });

  it('re-runs the dealer match when the shop name is corrected', async () => {
    recheckDealer.mockResolvedValue({ state: 'resolved', customerName: 'SANIMART SDN BHD' });
    render(<LodgeFlow live backend={backend()} />);
    await reachConfirm({ live: true });

    const input = screen.getByPlaceholderText(/shop name on your receipt/i);
    fireEvent.change(input, { target: { value: 'SANIMART SDN BHD' } });
    fireEvent.blur(input);

    await waitFor(() => expect(recheckDealer).toHaveBeenCalledWith(true, 'SANIMART SDN BHD'));
    // Only an exact match is echoed back. A candidate shown as a fact is how a purchase
    // gets attributed to a shop that never sold it. Asserted on the echo line rather than
    // the name, which also appears in the confirmation sentence above the input.
    await waitFor(() =>
      expect(screen.getByText(/we found them: SANIMART SDN BHD/i)).toBeInTheDocument(),
    );
  });

  it('does not echo a dealer name when the match was not exact', async () => {
    recheckDealer.mockResolvedValue(null);
    render(<LodgeFlow live backend={backend()} />);
    await reachConfirm({ live: true });

    const input = screen.getByPlaceholderText(/shop name on your receipt/i);
    fireEvent.change(input, { target: { value: 'SENG HUAT SDN BHD' } });
    fireEvent.blur(input);

    await waitFor(() => expect(recheckDealer).toHaveBeenCalled());
    expect(screen.queryByText(/we found them/i)).not.toBeInTheDocument();
  });

  it('shows a refused submission instead of swallowing it', async () => {
    render(
      <LodgeFlow
        backend={backend({
          submit: async () => {
            throw new Error(
              'No published consent notice exists, so personal data must not be collected.',
            );
          },
        })}
      />,
    );
    await reachSubmit();
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/consent notice/i),
    );
    // Still on the form, not on the confirmation. Telling a consumer "we have your report"
    // when nothing was stored is the worse of the two failures.
    expect(screen.queryByText(/we have your report/i)).not.toBeInTheDocument();
  });
});


/**
 * The photo step, which is where a real consumer either gets their receipt in or gives up.
 *
 * The first version of this tile assigned `setFiles(Array.from(...))` on every change, so a
 * second pick REPLACED the first. Somebody who attached the receipt and then went back for a
 * photo of the fault lost the receipt, and the counter still said a photo was ready - the
 * worst kind of wrong, because the screen looks correct.
 */
describe('lodge photo step', () => {
  function galleryInput() {
    return document.querySelectorAll('input[type="file"]')[0] as HTMLInputElement;
  }

  function file(name: string, contents = 'x') {
    return new File([contents], name, { type: 'image/jpeg' });
  }

  it('adds to what is already attached instead of replacing it', () => {
    render(<LodgeFlow live backend={backend()} />);
    const input = galleryInput();

    fireEvent.change(input, { target: { files: [file('receipt.jpg')] } });
    fireEvent.change(input, { target: { files: [file('fault.jpg')] } });

    expect(screen.getByText('2 photos ready.')).toBeInTheDocument();
    expect(screen.getByTitle('receipt.jpg')).toBeInTheDocument();
    expect(screen.getByTitle('fault.jpg')).toBeInTheDocument();
  });

  it('accepts a pasted screenshot, which is how most receipts arrive on a desktop', async () => {
    render(<LodgeFlow live backend={backend()} />);

    const pasted = file('screenshot.png');
    const event = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'clipboardData', { value: { files: [pasted] } });
    fireEvent(window, event);

    await waitFor(() => expect(screen.getByText('1 photo ready.')).toBeInTheDocument());
  });

  it('ignores the same file picked twice', () => {
    render(<LodgeFlow live backend={backend()} />);
    const input = galleryInput();
    const same = file('receipt.jpg');

    fireEvent.change(input, { target: { files: [same] } });
    fireEvent.change(input, { target: { files: [same] } });

    expect(screen.getByText('1 photo ready.')).toBeInTheDocument();
  });

  it('lets a mis-picked photo be removed', () => {
    render(<LodgeFlow live backend={backend()} />);
    const input = galleryInput();
    fireEvent.change(input, { target: { files: [file('receipt.jpg'), file('wrong.jpg')] } });
    expect(screen.getByText('2 photos ready.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove wrong.jpg' }));

    expect(screen.getByText('1 photo ready.')).toBeInTheDocument();
    expect(screen.queryByTitle('wrong.jpg')).not.toBeInTheDocument();
  });

  it('takes files dropped onto the tile', () => {
    render(<LodgeFlow live backend={backend()} />);
    const tile = screen.getByRole('button', { name: /add a photo/i }).parentElement as HTMLElement;

    fireEvent.drop(tile, { dataTransfer: { files: [file('dragged.jpg')] } });

    expect(screen.getByText('1 photo ready.')).toBeInTheDocument();
  });

  it('offers the camera as its own action rather than forcing it', () => {
    // `capture` on the main input forced the camera on a phone, which is what stopped a
    // consumer attaching a receipt they had already saved to their gallery.
    render(<LodgeFlow live backend={backend()} />);
    expect(galleryInput().hasAttribute('capture')).toBe(false);
    expect(screen.getByRole('button', { name: /take a photo now/i })).toBeInTheDocument();
  });
});

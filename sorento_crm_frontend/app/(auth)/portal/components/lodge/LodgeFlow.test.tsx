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
/**
 * The item step lists what the RECEIPT said, not Sorento's 31-kind catalogue. The Kind is
 * never asked: it decides warranty terms (ADR-0010), so it is Sorento's filing job, derived
 * from the model code or resolved by CS - not a consumer's guess.
 */
async function reachItems() {
  await reachConfirm();
  fireEvent.click(screen.getByRole('button', { name: /yes, that is right|continue/i }));
  await waitFor(() =>
    expect(screen.getByText(/which of these has the problem/i)).toBeInTheDocument(),
  );
}

async function reachSubmit() {
  await reachItems();
  // Every extracted line arrives pre-selected, so the ordinary path is to continue.
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
  it('lists the products the receipt named, not a catalogue', async () => {
    render(<LodgeFlow backend={backend()} />);
    await reachItems();
    // What the extraction returned, in the consumer's own receipt's words.
    expect(screen.getByText(/SRTWC8152 WATER CLOSET/i)).toBeInTheDocument();
    // And NOT the 31-kind grid this step used to be.
    expect(screen.queryByRole('button', { name: 'Urinal Bowl' })).not.toBeInTheDocument();
  });

  it('pre-selects every extracted line so the common case is one tap', async () => {
    render(<LodgeFlow backend={backend()} />);
    await reachItems();
    expect(screen.getByRole('button', { pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled();
  });

  it('blocks continuing when the consumer unticks everything', async () => {
    // A report naming no product is the one state worth refusing: CS has nothing to act on.
    render(<LodgeFlow backend={backend()} />);
    await reachItems();
    fireEvent.click(screen.getByRole('button', { pressed: true }));
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled();
  });

  it('asks the consumer to type what broke when nothing could be read', async () => {
    // No fallback to the catalogue: somebody who cannot see their product in a list has no
    // vocabulary to pick one from either, and free text is strictly more information than
    // a tile chosen by elimination.
    render(
      <LodgeFlow
        backend={backend({
          extract: async () => ({
            shop_name_raw: null,
            dealer: { state: 'unmatched', customer_name: null },
            purchase_date: null,
            document_number: null,
            sorento_order_number: null,
            lines: [],
          }),
        })}
      />,
    );
    // Navigated by hand rather than through `reachConfirm`: that helper waits for "did we
    // get this right", and the confirm step deliberately drops that sentence when there is
    // nothing to confirm - asking somebody to agree with an empty summary read as a broken
    // screen when the `unmatched` scenario was walked.
    fireEvent.click(screen.getByRole('button', { name: /add a photo/i }));
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /yes, that is right|^continue$/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /yes, that is right|^continue$/i }));
    await waitFor(() =>
      expect(screen.getByText(/could not read any products/i)).toBeInTheDocument(),
    );
    expect(screen.queryByRole('button', { name: 'Water Closet' })).not.toBeInTheDocument();
    // And it will not move on with nothing named.
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText(/the toilet seat/i), {
      target: { value: 'the flush button' },
    });
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled();
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
 * The photo step now uses the SAME `AttachmentDropzone` as every other portal submission.
 *
 * The bespoke tile that used to live here had to re-learn drag-and-drop, clipboard paste,
 * previews and removal one bug at a time, and had already lost photos once by replacing the
 * file list instead of appending to it. Those behaviours are the shared component's, and are
 * tested with it - what belongs HERE is that the lodge journey actually uses it, and that
 * the files it collects reach extraction.
 */
describe('lodge photo step', () => {
  it('uses the shared portal attachment component, not a bespoke tile', () => {
    render(<LodgeFlow live backend={backend()} />);
    // The shared dropzone's affordances. A regression to a hand-rolled input would take
    // clipboard paste and previews away without failing anything else.
    expect(screen.getByRole('button', { name: /choose file/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /paste from clipboard/i })).toBeInTheDocument();
  });

  it('will not extract until a file is actually attached', () => {
    render(<LodgeFlow live backend={backend()} />);
    expect(screen.getByRole('button', { name: /continue/i })).toBeDisabled();
  });

  it('hands the attached files to extraction', async () => {
    const extract = vi.fn().mockResolvedValue({
      shop_name_raw: 'TOTAL HOME DIY SDN BHD',
      dealer: { state: 'resolved', customer_name: 'TOTAL HOME DIY SDN BHD' },
      purchase_date: '2025-10-16',
      document_number: null,
      sorento_order_number: null,
      lines: [],
    });
    render(<LodgeFlow live backend={backend({ extract })} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['receipt'], 'receipt.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(screen.getByRole('button', { name: /continue/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    await waitFor(() => expect(extract).toHaveBeenCalled());
    const files = extract.mock.calls[0][1] as File[];
    expect(files.map((f) => f.name)).toEqual(['receipt.jpg']);
  });
});

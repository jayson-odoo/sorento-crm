/**
 * S3 Phase 2 - what the lodge flow talks to.
 *
 * The flow is written against this interface rather than against either implementation,
 * so the same screens serve two purposes that must not drift apart:
 *
 *   `mockLodgeBackend`  the `?scenario=` demo. Four extraction outcomes on demand, no
 *                       token, no receipt, no model call. It is how the flow gets
 *                       reviewed, and how the three non-happy paths stay walkable -
 *                       68% of receipts resolve, 8% land mid-band, 24% print no shop
 *                       name, and a prototype that can only demonstrate the first would
 *                       look finished while failing a quarter of real traffic.
 *
 *   `liveLodgeBackend`  the real endpoints, portal-token scoped.
 *
 * Two implementations of one interface, not two copies of one screen. A forked component
 * is how the demo and the real thing quietly stop agreeing about what the journey is.
 */
import {
  aiExtractFromFiles,
  CONSUMER_LODGE_FORM_KEY,
  fetchLodgeKinds,
  resolveLodge,
  submitLodge,
  summariseWarranty,
  type AIExtractResult,
  type LodgeSubmitInput,
} from '../../lib/portal-client';
import {
  MOCK_KINDS,
  mockExtract,
  mockSubmit,
  type ExtractResult,
  type LodgeResult,
  type MockScenario,
  type ProductKindTile,
} from './lodgeMocks';

export interface LodgeBackend {
  /** The tiled chooser (AC-C11). */
  kinds(): Promise<ProductKindTile[]>;
  /**
   * What the receipt said, as editable form state.
   *
   * `files` is empty on the mock backend, where `scenario` picks a canned outcome. On the
   * live backend the files ARE the receipt and the scenario is ignored.
   */
  extract(scenario: MockScenario, files?: File[]): Promise<ExtractResult>;
  submit(input: LodgeSubmitInput): Promise<LodgeResult>;
}

/**
 * Turn one AI-extract response into the shape the flow already renders.
 *
 * Exported for its own test rather than inlined: this map is where an extraction that read
 * the paper correctly can still end up wrong on screen, and every line of it is a decision.
 */
export function mapExtractToLodge(result: AIExtractResult): ExtractResult {
  const values = (result.values || {}) as Record<string, unknown>;
  const text = (key: string): string | null => {
    const raw = values[key];
    if (raw === null || raw === undefined) return null;
    const trimmed = String(raw).trim();
    return trimmed ? trimmed : null;
  };

  const lines = (result.products || []).map((line) => ({
    // Verbatim, and the only thing a CS agent can act on when the code resolves to
    // nothing - which is the ordinary outcome, not the exception.
    claimed_text: [line.product_code, line.product_name].filter(Boolean).join(' ').trim(),
    model_code_raw: line.product_code || null,
    // The KIND is resolved server-side from the code, never guessed here: cover is
    // decided from it (ADR-0010), so a frontend guess would be a warranty term.
    kind_code: null,
    kind_label: null,
    // Always null out of extraction. `SRTWC8152` matches three real variants and
    // resolves to none of them (AC-C17); the resolve call decides, and it usually
    // decides "ambiguous".
    product_id: null,
    quantity: typeof line.quantity === 'number' && line.quantity > 0 ? line.quantity : 1,
  }));

  return {
    shop_name_raw: text('shop_name'),
    // Extraction never states a dealer. It reads a NAME; `POST /lodge/resolve` decides
    // whether that name is a dealer, and only `resolved` is ever shown as one - three
    // receipts in thirty-eight had a real but WRONG nearest neighbour.
    dealer: { state: 'unmatched', customer_name: null },
    purchase_date: text('purchase_date'),
    document_number: text('dealer_document_number'),
    sorento_order_number: text('sorento_order_number'),
    lines,
    // Carried through untouched. What the extractor could read has no bearing on which
    // files were kept - the receipt it failed on is the one CS most needs to open.
    attachment_ids: result.attachment_ids ?? [],
  };
}

export const mockLodgeBackend: LodgeBackend = {
  kinds: async () => MOCK_KINDS,
  extract: (scenario) => mockExtract(scenario),
  submit: () => mockSubmit(),
};

export const liveLodgeBackend: LodgeBackend = {
  kinds: async () =>
    (await fetchLodgeKinds()).map((k) => ({
      code: k.kind_code,
      label: k.label,
      icon: k.icon,
    })),

  /**
   * Read the receipt, then fall back to an empty form rather than a dead end.
   *
   * **A failed extraction is not an error path.** 24% of receipts print no usable shop
   * name, phone cameras produce unreadable photos, and the model call can simply fail.
   * Every one of those must land the consumer on the same editable form with nothing
   * pre-filled, because that form is already the designed experience for "we could not
   * read much from that photo" - which is what the confirm step says. Throwing here would
   * turn the commonest imperfect case into a screen the consumer cannot get past, and
   * AC-C14 exists precisely to stop that.
   */
  extract: async (_scenario, files) => {
    const empty: ExtractResult = {
      shop_name_raw: null,
      dealer: { state: 'unmatched', customer_name: null },
      purchase_date: null,
      document_number: null,
      sorento_order_number: null,
      lines: [],
      // Overwritten below when the call succeeded: an extraction that read nothing off a
      // photo still stored the photo, and losing it here would discard the evidence in
      // exactly the case where a human has to look at it.
      attachment_ids: [],
    };
    if (!files || files.length === 0) return empty;
    try {
      return mapExtractToLodge(await aiExtractFromFiles(CONSUMER_LODGE_FORM_KEY, files));
    } catch {
      return empty;
    }
  },

  submit: async (input) => {
    const result = await submitLodge(input);
    return {
      complaint_number: result.complaint_number ?? result.complaint_id,
      // The engine answers per PART; a consumer reading five rows learns less than one
      // reading a sentence. The parts are still on the response for anyone who wants them.
      warranty: summariseWarranty(result.warranty),
    };
  },
};

/**
 * Re-check a shop name the consumer just corrected. Live only.
 *
 * Editing the shop name has to re-run the dealer match, or correcting a bad extraction
 * changes what is displayed without changing what is stored. Returns null on the mock
 * backend, where there is no customer table to match against.
 */
export async function recheckDealer(
  live: boolean,
  shopName: string,
): Promise<{ state: string; customerName: string | null } | null> {
  if (!live || !shopName.trim()) return null;
  try {
    const result = await resolveLodge({ shop_name: shopName, lines: [] });
    return { state: result.dealer.state, customerName: result.dealer.customer_name };
  } catch {
    // A failed re-check must never block the form. The shop name the consumer typed is
    // kept either way (AC-C14) and CS resolves it if we could not.
    return null;
  }
}

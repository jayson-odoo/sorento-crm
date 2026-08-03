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
  fetchLodgeKinds,
  resolveLodge,
  submitLodge,
  summariseWarranty,
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
  /** What the receipt said, as editable form state. */
  extract(scenario: MockScenario): Promise<ExtractResult>;
  submit(input: LodgeSubmitInput): Promise<LodgeResult>;
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
   * Live extraction is not wired to a receipt yet, so this resolves what the consumer
   * has typed rather than pretending to read a photo.
   *
   * Deliberate: `POST /portal/ai-extract` already reads receipts and returns a generic
   * per-form shape, and mapping it onto this journey is its own piece of work. Returning
   * an empty-but-honest result keeps the live flow usable - the consumer types the shop
   * name and gets a real dealer match against the real customer table - instead of
   * blocking the whole path on the model call.
   */
  extract: async () => ({
    shop_name_raw: null,
    dealer: { state: 'unmatched', customer_name: null },
    purchase_date: null,
    document_number: null,
    sorento_order_number: null,
    lines: [],
  }),

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

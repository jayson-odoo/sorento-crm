/**
 * S3 Phase 1 - the consumer intake contract, as mocks.
 *
 * Phase 1 is frontend-first on purpose: the flow gets tuned against stubbed data before a
 * single endpoint exists, so a UX disagreement surfaces against a clickable screen instead
 * of a deployed feature. Everything here is deleted in Phase 2 except the shapes, which
 * become the API contract.
 *
 * ## The contract Phase 2 must satisfy
 *
 * ```
 * POST /api/v1/public/portal/complaints/extract   { attachment_ids: [...] }
 * -> ExtractResult
 * ```
 *
 * `dealer.state` is the load-bearing field, and it is a STATE rather than a confidence
 * float. That is a finding from the S3-pre spike, not a preference: dealer match scores
 * came back bimodal - 26 of 38 receipts matched at exactly 1.00 and NOTHING landed between
 * 0.70 and 0.99 - so there is no gradient for a frontend to threshold, and three receipts
 * in the middle band named a real but WRONG dealer (`SENG HUAT` resolving to `CHENG HUAT
 * HARDWARE`). A float invites each caller to invent its own cutoff and eventually to
 * pre-fill one of those. See `documentation/plans/after-sales/S3-pre-extraction-accuracy.md`.
 *
 * - `resolved`   - exact match after normalisation. Pre-fills the dealer. 68% of receipts.
 * - `candidate`  - something matched, not well enough to assert. NEVER pre-fills; the
 *                  consumer sees only their own typed shop name, and CS sees the suggestion.
 * - `unmatched`  - no match, or no shop name printed at all. Submission proceeds anyway
 *                  (AC-C14), carrying the raw text for CS.
 *
 * The consumer is never shown a dealer picker or a customer code (AC-C11), so `candidate`
 * and `unmatched` look identical from their side. The difference is only in what CS receives.
 */

export type DealerMatchState = 'resolved' | 'candidate' | 'unmatched';

export interface ExtractedLine {
  /** Verbatim line text from the receipt - what the consumer actually claimed. */
  claimed_text: string;
  /** Model code as printed, before any resolution. */
  model_code_raw: string | null;
  /** Resolved Warranty Product Kind, or null when the code was ambiguous. */
  kind_code: string | null;
  kind_label: string | null;
  /** Deliberately null when a base code matches several variants (AC-C17). */
  product_id: string | null;
  quantity: number;
}

export interface ExtractResult {
  /** What was printed at the top of the receipt, verbatim. Always editable. */
  shop_name_raw: string | null;
  dealer: {
    state: DealerMatchState;
    /** Only populated when state is `resolved`. Never rendered to a consumer. */
    customer_name: string | null;
  };
  /** ISO date, or null when nothing legible was found. */
  purchase_date: string | null;
  /** The dealer's own document number - never matched against Sorento orders (AC-C12). */
  document_number: string | null;
  /** Set only on the dealer track, where the order resolves everything (AC-C13). */
  sorento_order_number: string | null;
  lines: ExtractedLine[];
}

/** The tiled chooser reads these. 31 in production; a representative set here. */
export interface ProductKindTile {
  code: string;
  label: string;
  /** VARCHAR(64) icon slug. Zero of the 31 rows carry one today - the tiles fall back to
   *  an initial, which is exactly the gap this prototype is meant to make visible. */
  icon: string | null;
}

export const MOCK_KINDS: ProductKindTile[] = [
  { code: 'water_closet', label: 'Water Closet', icon: null },
  { code: 'wash_basin', label: 'Wash Basin', icon: null },
  { code: 'kitchen_mixer_tap', label: 'Kitchen Mixer Tap', icon: null },
  { code: 'kitchen_bathroom_cold_tap', label: 'Kitchen & Bathroom Cold Tap', icon: null },
  { code: 'kitchen_bathroom_mixer_tap', label: 'Kitchen & Bathroom Mixer Tap', icon: null },
  { code: 'hand_shower', label: 'Hand Shower', icon: null },
  { code: 'exposed_shower_set', label: 'Exposed Shower Set', icon: null },
  { code: 'kitchen_sink_ss304', label: 'Kitchen Sink', icon: null },
  { code: 'led_mirror', label: 'LED Mirror', icon: null },
  { code: 'mirror_cabinet', label: 'Mirror Cabinet', icon: null },
  { code: 'squatting_pan', label: 'Squatting Pan', icon: null },
  { code: 'hand_bidet', label: 'Hand Bidet', icon: null },
  { code: 'stop_valve', label: 'Stop Valve', icon: null },
  { code: 'sensor_tap', label: 'Sensor Taps', icon: null },
  { code: 'urinal_bowl', label: 'Urinal Bowl', icon: null },
  { code: 'bathroom_furniture', label: 'Bathroom Furniture', icon: null },
];

/**
 * The four extraction outcomes worth designing against.
 *
 * They are not "happy path plus errors": three of the four are normal traffic. 68% resolve,
 * 8% land mid-band, 24% carry no usable shop name, and 24% quote a Sorento order number.
 * A prototype tuned only on `resolved` would look finished and fall over on a quarter of
 * real receipts.
 */
export type MockScenario = 'resolved' | 'candidate' | 'unmatched' | 'dealer_track';

export const MOCK_EXTRACTS: Record<MockScenario, ExtractResult> = {
  resolved: {
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
  },
  candidate: {
    // The real failure mode from the spike: a plausible but wrong neighbour.
    shop_name_raw: 'SENG HUAT SDN BHD',
    dealer: { state: 'candidate', customer_name: null },
    purchase_date: '2023-02-11',
    document_number: 'CS002629',
    sorento_order_number: null,
    lines: [
      {
        claimed_text: 'WC189-G2 TOILET BOWL',
        model_code_raw: 'WC189-G2',
        kind_code: 'water_closet',
        kind_label: 'Water Closet',
        product_id: null,
        quantity: 1,
      },
    ],
  },
  unmatched: {
    // 13% of receipts print no trading name at all - only a document number.
    shop_name_raw: null,
    dealer: { state: 'unmatched', customer_name: null },
    purchase_date: null,
    document_number: 'B10-2-26050837',
    sorento_order_number: null,
    lines: [
      {
        claimed_text: 'TAP SET',
        model_code_raw: null,
        kind_code: null,
        kind_label: null,
        product_id: null,
        quantity: 1,
      },
    ],
  },
  dealer_track: {
    shop_name_raw: 'SORENTO SDN BHD',
    dealer: { state: 'resolved', customer_name: 'LIM SENG HARDWARE SDN BHD' },
    purchase_date: '2026-04-29',
    document_number: null,
    sorento_order_number: '202604-0348',
    lines: [
      {
        claimed_text: 'SRTWC8517-200 WATER CLOSET',
        model_code_raw: 'SRTWC8517-200',
        kind_code: 'water_closet',
        kind_label: 'Water Closet',
        product_id: null,
        quantity: 2,
      },
    ],
  },
};

/** Stubbed extraction. Phase 2 replaces the body, never the signature. */
export async function mockExtract(scenario: MockScenario): Promise<ExtractResult> {
  await new Promise((resolve) => setTimeout(resolve, 1400));
  return MOCK_EXTRACTS[scenario];
}

export interface PhotoCheck {
  passed: boolean;
  /** Plain language, imperative, and about the SHOT - never about the person. */
  suggestion: string | null;
}

/**
 * Stubbed photo validation (S2a's validator, seen from the consumer's side).
 *
 * Advisory, never blocking (AC-C14 / AC-M27): a nudge appears, a retake is offered, and
 * submission proceeds either way. The second photo of any batch fails here so the retake
 * affordance is always exercised in the prototype.
 */
export async function mockCheckPhoto(index: number): Promise<PhotoCheck> {
  await new Promise((resolve) => setTimeout(resolve, 900));
  if (index % 2 === 1) {
    return {
      passed: false,
      suggestion: 'Step back a little so the pipe joint is in the shot.',
    };
  }
  return { passed: true, suggestion: null };
}

export interface LodgeResult {
  complaint_number: string;
  warranty: {
    /** covered | expired | needs_review - the verdict S2's engine computes. */
    state: 'covered' | 'expired' | 'needs_review';
    summary: string;
  };
}

export async function mockSubmit(): Promise<LodgeResult> {
  await new Promise((resolve) => setTimeout(resolve, 1200));
  return {
    complaint_number: 'CMP2026-0148',
    warranty: {
      state: 'covered',
      summary: 'Ceramic body - covered against cracking and leaking for as long as you own it.',
    },
  };
}

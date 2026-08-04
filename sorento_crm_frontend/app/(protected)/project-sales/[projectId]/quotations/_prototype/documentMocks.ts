/**
 * Phase 1 fixtures for the quotation DOCUMENT, taken off the real artifact.
 *
 * Source: `Cabana Elmina - nadi cergas R2.xlsx` (Sorento → Nadi Cergas, 26/02/2026,
 * TOTAL AMOUNT RM 696,923). Real numbers on purpose: a prototype priced with round
 * invented figures hides exactly the problems this screen exists to surface - a
 * 1,046-unit quantity next to a RM 1.50 floor trap, five `rate only` lines that must
 * not be summed, and a total long enough to test the column width.
 *
 * The sample is one sheet with bands; the client's other projects split those bands
 * into tabs (townhouse / guard house / reception). Both are modelled here so the
 * screen is exercised the way both kinds of project will use it.
 *
 * NOTHING here survives Phase 2. The contract these shapes document is at the top of
 * the service file that replaces them.
 */

export type MockLine = {
  id: string;
  /** The A / B / C letter. Blank on a sub-line that belongs to the letter above it. */
  item_label: string | null;
  /** Starts a band when set; null continues the band above. */
  band_label: string | null;
  description: string;
  technical_spec: string | null;
  brand: string | null;
  product_code: string | null;
  quantity: number;
  unit_rate: number;
  complete_set: string | null;
  /** Quoted and printed, excluded from every total. */
  is_rate_only: boolean;
  image_url: string | null;
};

export type MockScope = {
  id: string;
  label: string;
  outcome: 'open' | 'won' | 'lost';
  lines: MockLine[];
};

/**
 * The document's own rungs, shaped like a status graph rather than a hardcoded enum, because
 * the primary CTA is derived from the graph exactly as it is on the project header. The client:
 * "our call to action for quotation is move to next stage ma, which should be based on our
 * status graph lo". Phase 2 reads these from `statuses` / `status_transitions`.
 */
export type MockStatus = {
  id: string;
  label: string;
  sort_order: number;
  is_terminal: boolean;
};

export type MockTransition = {
  id: string;
  from_status_id: string;
  to_status_id: string;
  /** What the admin called this edge, which is what the button says. */
  label: string;
};

export const MOCK_STATUSES: MockStatus[] = [
  { id: 'st-draft', label: 'Draft', sort_order: 1, is_terminal: false },
  { id: 'st-issued', label: 'Issued', sort_order: 2, is_terminal: false },
  { id: 'st-accepted', label: 'Accepted', sort_order: 3, is_terminal: true },
  { id: 'st-withdrawn', label: 'Withdrawn', sort_order: 4, is_terminal: true },
];

export const MOCK_TRANSITIONS: MockTransition[] = [
  { id: 'tr-1', from_status_id: 'st-draft', to_status_id: 'st-issued', label: 'Issue R3' },
  {
    id: 'tr-2',
    from_status_id: 'st-issued',
    to_status_id: 'st-accepted',
    label: 'Mark accepted',
  },
  // Backward and terminal edges are real moves and stay available, behind the gear, because a
  // correction or an exit should be deliberate. Same rule as the project header.
  { id: 'tr-3', from_status_id: 'st-issued', to_status_id: 'st-draft', label: 'Back to draft' },
  {
    id: 'tr-4',
    from_status_id: 'st-issued',
    to_status_id: 'st-withdrawn',
    label: 'Withdraw',
  },
];

export type MockDocument = {
  id: string;
  document_no: string;
  issue_label: string | null;
  your_ref: string | null;
  doc_date: string;
  status_id: string;
  sender: { name: string; lines: string[]; tel: string };
  recipient: { name: string; lines: string[]; phones: string[] };
  attn_name: string | null;
  subject_title: string;
  cover_letter: string;
  terms: string[];
  signatory: { name: string; phone: string };
  signed_at: string | null;
  signature_ip: string | null;
  signature_gps: string | null;
  customer_signed_at: string | null;
  scopes: MockScope[];
};

function line(
  id: string,
  description: string,
  brand: string | null,
  product_code: string | null,
  quantity: number,
  unit_rate: number,
  extra: Partial<MockLine> = {},
): MockLine {
  return {
    id,
    item_label: null,
    band_label: null,
    technical_spec: null,
    complete_set: null,
    is_rate_only: false,
    image_url: null,
    description,
    brand,
    product_code,
    quantity,
    unit_rate,
    ...extra,
  };
}

/** Bill no 3, pages 15/4 to 15/6 of the sample: the apartment units themselves. */
const HOUSE_UNITS: MockLine[] = [
  line('l1', 'CLOSED COUPLED WASHDOWN WATER CLOSET WITH SOFT CLOSE SEAT', 'CABANA', 'CWC604-RL', 1046, 250, {
    item_label: 'A',
    band_label: 'BILL NO 3 PAGE 15/4',
  }),
  line('l2', 'ONE PIECE WASHDOWN WATER CLOSET WITH SOFT CLOSE SEAT', 'CABANA', 'CWC7601-S-RL', 1, 220, {
    band_label: 'OPTION',
    is_rate_only: true,
  }),
  line('l3', 'CLOSED COUPLED WASHDOWN WATER CLOSET (ALTERNATE)', 'CABANA', 'CWC605-RL', 1046, 180, {
    is_rate_only: true,
  }),
  line('l4', 'STAINLESS STEEL ANGLE VALVE WITH MATT FINISH', 'CABANA', 'B2155-BLUE', 1046, 8),
  line('l5', 'HIGH PRESSURE PREMIUM REINFORCE FLEXIBLE HOSE', 'CABANA', 'C-FH 14', 1046, 5),
  line('l6', 'WALL HUNG WASH BASIN', 'CABANA', 'CGB762', 1035, 60, { item_label: 'B' }),
  line('l7', 'WALL HUNG WASH BASIN (ALTERNATE)', 'CABANA', 'CWB 242', 1035, 45, { is_rate_only: true }),
  line('l8', 'PLASTIC BOTTLE TRAP WITH WASTE PLUG AND CHAIN', null, 'TPE 9203', 1035, 6.5),
  line('l9', 'STAINLESS STEEL ANGLE VALVE WITH MATT FINISH', 'CABANA', 'B2155-BLUE', 1035, 8),
  line('l10', 'HIGH PRESSURE PREMIUM REINFORCE FLEXIBLE HOSE', 'CABANA', 'C-FH 14', 1035, 5),
  line('l11', 'STAINLESS STEEL BASIN COLD TAP', 'CABANA', 'CB 60SS-DIY', 1035, 18, { item_label: 'C' }),
  line('l12', 'STAINLESS STEEL ANGLE VALVE WITH MATT FINISH', 'CABANA', 'CB1500SS', 1046, 12, {
    item_label: 'D',
  }),
  line('l13', 'HAND BIDET, WALL BRACKET AND FLEXIBLE HOSE', 'CABANA', 'CB81CR', 1046, 15),
  line('l14', 'SLIDING BAR + SOAP HOLDER C/W 3 FUNCTION HAND SHOWER', 'SORENTO', 'SRTSS8780', 1046, 108, {
    item_label: 'C',
    band_label: 'BILL NO 3 PAGE 15/5',
  }),
  line('l15', 'STOP VALVE', 'CABANA', 'CSK11A', 1046, 42),
  line('l16', 'SHOWER UNION', 'CABANA', 'CB2320', 1046, 30),
  line('l17', 'POLISHED SURFACE STAINLESS STEEL PAPER HOLDER', 'CABANA', 'CB310-CR', 1046, 15, {
    item_label: 'D',
  }),
  line('l18', 'PVC FLOOR TRAP', null, null, 1046, 1.5, { item_label: 'F' }),
  line('l19', 'STAINLESS STEEL TOP MOUNT SINGLE BOWL SINK', 'CABANA', 'CSK806', 523, 72, {
    item_label: 'A',
    band_label: 'BILL NO 3 PAGE 15/6',
  }),
  line('l20', 'WALL MOUNTED STAINLESS STEEL KITCHEN SINK TAP', 'CABANA', 'CB1508ASS', 523, 20, {
    item_label: 'B',
  }),
  line('l21', 'STAINLESS STEEL HOSE BIB TAP', 'CABANA', 'CB 1505SS', 1046, 13, { item_label: 'C' }),
  line('l22', 'WASHING MACHINE FLOOR TRAP 150 X 150MM', 'SORENTO', 'SRT382-6', 523, 17, {
    item_label: 'E',
  }),
];

/** Page 15/5's OKU items: the handicapped toilet, quoted as its own space. */
const OKU_TOILET: MockLine[] = [
  line('o1', 'WALL HUNG HANDICAPPED WASH BASIN', 'MOCHA', 'MWB7621', 11, 310, {
    item_label: 'A',
    band_label: 'BILL NO 3 PAGE 15/5',
  }),
  line('o2', 'PLASTIC BOTTLE TRAP WITH WASTE PLUG AND CHAIN', null, 'TPE 9203', 11, 6.5),
  line('o3', 'STAINLESS STEEL ANGLE VALVE WITH MATT FINISH', 'CABANA', 'B2155-BLUE', 11, 8),
  line('o4', 'PILLAR MOUNTED BRASS ELBOW ACTION TAP', 'SORENTO', 'SRTSC07', 11, 90, { item_label: 'B' }),
  line('o5', 'GRAB BAR WITH 32MM DIAMETER', 'SORENTO', 'SRT392B-16', 11, 71, { item_label: 'E' }),
  line('o6', 'STAINLESS STEEL GRAB BAR', 'SORENTO', 'SRT5674', 1, 150, {
    band_label: 'OPTIONAL ITEMS FOR OKU TOILET',
    is_rate_only: true,
  }),
  line('o7', 'STAINLESS STEEL GRAB BAR', 'SORENTO', 'SRT5732', 1, 240, { is_rate_only: true }),
];

/** Page 15/7 - 15/8: the management office and the common areas. */
const COMMON_AREA: MockLine[] = [
  line('c1', 'WALL HUNG WASH BASIN', 'CABANA', 'CWB 242', 1, 45, {
    item_label: 'A',
    band_label: 'BILL NO 3 PAGE 15/7',
  }),
  line('c2', 'PLASTIC BOTTLE TRAP WITH WASTE PLUG AND CHAIN', null, 'TPE 9203', 1, 6.5),
  line('c3', 'STAINLESS STEEL BASIN COLD TAP', 'CABANA', 'CB 60SS-DIY', 1, 18, { item_label: 'B' }),
  line('c4', 'STAINLESS STEEL ANGLE VALVE WITH MATT FINISH', 'CABANA', 'CB1500SS', 2, 12, {
    item_label: 'C',
  }),
  line('c5', 'HAND BIDET, WALL BRACKET AND FLEXIBLE HOSE', 'CABANA', 'CB81CR', 2, 15),
  line('c6', 'STAINLESS STEEL TOP MOUNT SINGLE BOWL SINK', 'CABANA', 'CSK806', 1, 72, {
    item_label: 'E',
  }),
  line('c7', 'STAINLESS STEEL HOSE BIB TAP', 'CABANA', 'CB 1505SS', 37, 13, { item_label: 'G' }),
  line('c8', 'PVC FLOOR TRAP', null, null, 118, 1.5, {
    item_label: 'A',
    band_label: 'BILL NO 3 PAGE 15/8',
  }),
  line('c9', 'STAINLESS STEEL FLOOR GRATING WITH INSET TRAY', null, 'CB6633', 3, 13, {
    item_label: 'B',
  }),
];

export const MOCK_DOCUMENT: MockDocument = {
  id: 'mock-doc-1',
  document_no: 'SRT/Q/2026/0141',
  issue_label: 'R2',
  your_ref: null,
  doc_date: '2026-02-26',
  status_id: 'st-issued',
  sender: {
    name: 'SORENTO SDN BHD (694526-P)',
    lines: ['NO 5, JALAN ASTANA 2/KU2', 'BANDAR BUKIT RAJA', '41050 KLANG SELANGOR'],
    tel: '03-3082 9288',
  },
  recipient: {
    name: 'Nadi Cergas Sdn Bhd',
    lines: ['F-1@8 Suria', 'Jln PJU 1/42', '47301 Petaling Jaya Selangor'],
    phones: ['03-7887 3388', '03-7887 3377'],
  },
  attn_name: 'Kelly',
  subject_title: 'CADANGAN MEMBINA PANGSAPURI RUMAH IDAM',
  cover_letter:
    'Dear Kelly,\n\nThank you for the opportunity to quote for CADANGAN MEMBINA PANGSAPURI RUMAH IDAM. ' +
    'Please find our revised offer enclosed, covering the apartment units, the OKU toilets and the ' +
    'common areas.\n\nAll items are supplied to the specification agreed on site, and our team is ' +
    'available to walk the mock-up unit with you before the order is placed.',
  terms: [
    'Prices quoted in Ringgit Malaysia (RM), including delivery to site.',
    'Validity: this programme is valid for one year from the date of this quotation.',
    'The delivery shall be subjected to stock availability at the time of order.',
    'Prices quoted INCLUDE Sales & Service Tax (SST).',
    'Any variation and / or fluctuation in the currency exchange rate may revise the prices quoted.',
    'Any increase in raw material cost and / or import duty may revise the prices quoted.',
    'Payment term: 60 days subject to approval of credit facility.',
    'DISCLAIMER: while every effort has been made to ensure accuracy, product images and finishes are indicative.',
  ],
  signatory: { name: 'BASER RAMLI', phone: '019-350 8781' },
  signed_at: '2026-02-26T10:48:55',
  signature_ip: '203.106.14.72',
  signature_gps: null,
  customer_signed_at: null,
  scopes: [
    { id: 's1', label: 'Apartment units', outcome: 'open', lines: HOUSE_UNITS },
    { id: 's2', label: 'OKU toilets', outcome: 'open', lines: OKU_TOILET },
    { id: 's3', label: 'Common areas', outcome: 'open', lines: COMMON_AREA },
  ],
};

/** A rate-only line has a rate but no amount, and contributes nothing (AC-C2). */
export function lineAmount(row: MockLine): number | null {
  if (row.is_rate_only) return null;
  return row.quantity * row.unit_rate;
}

export function scopeTotal(scope: MockScope): number {
  return scope.lines.reduce((sum, row) => sum + (lineAmount(row) ?? 0), 0);
}

export function documentTotal(document: MockDocument): number {
  return document.scopes.reduce((sum, scope) => sum + scopeTotal(scope), 0);
}

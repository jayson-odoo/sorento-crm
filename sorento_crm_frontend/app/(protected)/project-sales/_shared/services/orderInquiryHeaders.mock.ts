/**
 * Phase 1 fixture for the OI DOCUMENT (header) screens (`PLAN-oi-header-list-detail.md`).
 *
 * Everything in this module is in-process data - no `apiFetch`, no network. It is the ONE
 * place Phase 1's mock lives, so Phase 2 (S2/S3) swaps `orderInquiryService.ts`'s header
 * functions to call the real `GET /api/v1/projects/order-inquiry-headers*` routes without
 * the hooks or the UI ever knowing the difference.
 *
 * Coverage (plan's "facts to save you searching"): outstanding + completed headers, a
 * header with 0 linked documents (`oih-5`), a header with 40+ lines (`oih-6`), long
 * customer/project text that must truncate (`oih-2`), and a header whose lines are ALL
 * cancelled so it reads Completed with zero counted lines (`oih-4`, AC-LS-02).
 */

import type {
  OrderInquiryHeader,
  OrderInquiryHeaderDetail,
  OrderInquiryHeaderListParams,
  OrderInquiryHeaderRaiseEntry,
  OrderInquiryHeaderRelatedDocuments,
  OrderInquiryWorklistRow,
} from '../types/orderInquiry.types';

interface MockHeaderSeed {
  id: string;
  inquiry_no: string;
  legacy_inquiry_no?: string | null;
  raised_at: string;
  raised_by_name: string;
  sales_order_id: string | null;
  project_sales_order_id: string | null;
  so_number: string | null;
  so_date: string | null;
  order_type?: string | null;
  customer_name: string;
  customer_code: string;
  project_id: string | null;
  project_title: string | null;
  agent_name: string | null;
  raise_history: OrderInquiryHeaderRaiseEntry[];
}

const HEADER_SEEDS: MockHeaderSeed[] = [
  {
    id: 'oih-1',
    inquiry_no: 'OI-2609-0001',
    raised_at: '2026-09-08T02:15:00',
    raised_by_name: 'Amirah Zulkifli',
    sales_order_id: 'so-410021',
    project_sales_order_id: 'pso-410021',
    so_number: 'SO410021',
    so_date: '2026-09-07',
    order_type: 'Local sale',
    customer_name: 'Sri Utama Sdn Bhd',
    customer_code: 'C-1021',
    project_id: 'proj-1',
    project_title: 'Sri Utama Tower Fit-out',
    agent_name: 'Daniel Wong',
    raise_history: [
      { kind: 'raised', by_name: 'Amirah Zulkifli', at: '2026-09-08T02:15:00' },
      { kind: 'reconfirmed', by_name: 'Amirah Zulkifli', at: '2026-09-12T05:40:00' },
    ],
  },
  {
    id: 'oih-2',
    inquiry_no: 'OI-2609-0002',
    raised_at: '2026-09-09T03:05:00',
    raised_by_name: 'Amirah Zulkifli',
    sales_order_id: 'so-410022',
    project_sales_order_id: 'pso-410022',
    so_number: 'SO410022',
    so_date: '2026-09-08',
    customer_name: 'PT Kencana Industri Perkasa Manufacturing And Trading Sdn Bhd',
    customer_code: 'C-2098',
    project_id: 'proj-2',
    project_title:
      'Integrated Facility Redevelopment And Modernisation Programme, Phase 2 (Block C)',
    agent_name: 'Daniel Wong',
    raise_history: [{ kind: 'raised', by_name: 'Amirah Zulkifli', at: '2026-09-09T03:05:00' }],
  },
  {
    id: 'oih-3',
    inquiry_no: 'OI-2609-0003',
    raised_at: '2026-09-09T06:50:00',
    raised_by_name: 'Farid Hassan',
    sales_order_id: 'so-410015',
    project_sales_order_id: null,
    so_number: 'SO410015',
    so_date: '2026-09-09',
    customer_name: 'Menara Utara Development Sdn Bhd',
    customer_code: 'C-1509',
    project_id: null,
    project_title: null,
    agent_name: 'Siti Rahman',
    raise_history: [{ kind: 'raised', by_name: 'Farid Hassan', at: '2026-09-09T06:50:00' }],
  },
  {
    id: 'oih-4',
    inquiry_no: 'OI-2609-0004',
    legacy_inquiry_no: 'OI-000318',
    raised_at: '2026-09-08T01:20:00',
    raised_by_name: 'Farid Hassan',
    sales_order_id: 'so-410009',
    project_sales_order_id: null,
    so_number: 'SO410009',
    so_date: '2026-09-07',
    customer_name: 'Global Trading Co',
    customer_code: 'C-0090',
    project_id: null,
    project_title: null,
    agent_name: null,
    raise_history: [{ kind: 'raised', by_name: 'Farid Hassan', at: '2026-09-08T01:20:00' }],
  },
  {
    id: 'oih-5',
    inquiry_no: 'OI-2609-0005',
    raised_at: '2026-09-12T04:00:00',
    raised_by_name: 'Amirah Zulkifli',
    sales_order_id: 'so-410030',
    project_sales_order_id: 'pso-410030',
    so_number: 'SO410030',
    so_date: '2026-09-11',
    customer_name: 'Bina Jaya Holdings',
    customer_code: 'C-3301',
    project_id: 'proj-3',
    project_title: 'Bina Jaya Warehouse Extension',
    agent_name: 'Siti Rahman',
    raise_history: [{ kind: 'raised', by_name: 'Amirah Zulkifli', at: '2026-09-12T04:00:00' }],
  },
  {
    id: 'oih-6',
    inquiry_no: 'OI-2609-0006',
    raised_at: '2026-09-13T07:30:00',
    raised_by_name: 'Farid Hassan',
    sales_order_id: 'so-410035',
    project_sales_order_id: 'pso-410035',
    so_number: 'SO410035',
    so_date: '2026-09-12',
    customer_name: 'Utama Builders Sdn Bhd',
    customer_code: 'C-4102',
    project_id: 'proj-4',
    project_title: 'Utama Builders Depot Fit-out',
    agent_name: 'Daniel Wong',
    raise_history: [{ kind: 'raised', by_name: 'Farid Hassan', at: '2026-09-13T07:30:00' }],
  },
  {
    id: 'oih-7',
    inquiry_no: 'OI-2609-0007',
    raised_at: '2026-09-14T08:10:00',
    raised_by_name: 'Siti Rahman',
    // Adopted-order edge case (measured facts): no core sales order reached, so the
    // S/O no column and the header's own link render as plain text (AC-HL-06).
    sales_order_id: null,
    project_sales_order_id: null,
    so_number: 'SO410040',
    so_date: '2026-09-13',
    customer_name: 'Kota Damai Enterprise',
    customer_code: 'C-5009',
    project_id: null,
    project_title: null,
    agent_name: 'Siti Rahman',
    raise_history: [{ kind: 'raised', by_name: 'Siti Rahman', at: '2026-09-14T08:10:00' }],
  },
];

let lineSeq = 0;
function nextLineId(headerId: string): string {
  lineSeq += 1;
  return `${headerId}-line-${lineSeq}`;
}

/** `raised` (no link), `placed` (linked quantity covers the whole line) or
 * `partly_linked` (some of it) - the same three-way read `OrderInquiryStatePill` and the
 * detail page's own `isLinkable`/`selectedLinked` derive it by, off the line's OWN
 * `links`, so a fixture line's state can never disagree with what it is linked to
 * (browser-pass DEFECT, fix round: every fixture line read `raised` regardless of its
 * links, so a ticked linked line could never enable Unlink selected). */
function deriveLineState(
  qty: string,
  links: OrderInquiryWorklistRow['links'],
): 'raised' | 'placed' | 'partly_linked' {
  const linkedQty = (links ?? []).reduce((sum, link) => sum + Number(link.qty || '0'), 0);
  const total = Number(qty || '0');
  if (linkedQty <= 0) return 'raised';
  if (linkedQty >= total) return 'placed';
  return 'partly_linked';
}

/** One mock line. `ackState` decides whether it counts toward `lines_to_confirm`; `state`
 * is DERIVED from `qty`/`links` when the caller does not state one explicitly (the
 * cancelled fixtures do, since cancellation is not a fact `links` alone could ever say). */
function buildLine(
  headerId: string,
  overrides: Partial<OrderInquiryWorklistRow> & {
    ackState?: 'awaiting' | 'acknowledged' | 'changed' | 'rejected';
  },
): OrderInquiryWorklistRow {
  const { ackState = 'acknowledged', qty = '10', links = [], state, ...rest } = overrides;
  return {
    id: nextLineId(headerId),
    inquiry_no: undefined,
    item_code: 'SKU-0000',
    product_name: null,
    delivery_date: '2026-10-01',
    customer_name: null,
    project_title: null,
    supplier: null,
    location: null,
    verb: 'ORDER',
    note: null,
    ...rest,
    qty,
    links,
    state: state ?? deriveLineState(qty, links),
    ack_state: ackState,
  };
}

const LINES_BY_HEADER: Record<string, OrderInquiryWorklistRow[]> = {
  'oih-1': [
    buildLine('oih-1', {
      item_code: 'CKSW015',
      product_name: 'Ceramic Kitchen Sink 015',
      qty: '40',
      delivery_date: '2026-09-25',
      supplier: 'Sunrise Ceramics Sdn Bhd',
      location: 'PJ-WH01',
      verb: 'ORDER',
      ackState: 'awaiting',
      links: [],
    }),
    buildLine('oih-1', {
      item_code: 'TAP-220',
      product_name: 'Chrome Basin Tap 220',
      qty: '18',
      delivery_date: '2026-09-25',
      supplier: 'Sunrise Ceramics Sdn Bhd',
      location: 'PJ-WH01',
      verb: 'ORDER',
      ackState: 'acknowledged',
      links: [
        {
          id: 'oih-1-link-1',
          kind: 'po',
          document: '202609-S0041',
          qty: '18',
          po_id: 'po-1',
        },
      ],
    }),
    buildLine('oih-1', {
      item_code: 'GRT-090',
      product_name: 'Porcelain Floor Tile 090',
      qty: '600',
      delivery_date: '2026-10-02',
      supplier: 'Sunrise Ceramics Sdn Bhd',
      location: 'PJ-WH01',
      verb: 'ORDER',
      ackState: 'changed',
      previous_qty: '500',
      previous_delivery_date: '2026-09-28',
      links: [
        {
          id: 'oih-1-link-2',
          kind: 'po',
          document: '202609-S0041',
          qty: '500',
          po_id: 'po-1',
        },
      ],
    }),
    buildLine('oih-1', {
      item_code: 'DR-HDL-12',
      product_name: 'Brushed Nickel Door Handle',
      qty: '24',
      delivery_date: '2026-09-30',
      supplier: 'Metroline Hardware',
      location: 'PJ-WH01',
      verb: 'ORDER_BACK',
      ackState: 'acknowledged',
      links: [
        { id: 'oih-1-link-3', kind: 'spo', document: 'SPO-2026/09-0012', qty: '24' },
      ],
    }),
    buildLine('oih-1', {
      item_code: 'PNT-WHT-20',
      product_name: 'Interior Emulsion Paint, White, 20L',
      qty: '30',
      delivery_date: '2026-10-05',
      supplier: 'Metroline Hardware',
      location: 'PJ-WH01',
      verb: 'ADVANCE',
      note: 'Moved forward from 20/10/2026 - site handover brought in',
      ackState: 'acknowledged',
      links: [
        { id: 'oih-1-link-4', kind: 'po', document: '202609-S0055', qty: '30', po_id: 'po-2' },
      ],
    }),
    buildLine('oih-1', {
      item_code: 'CBL-004',
      product_name: 'Cable duct, cancelled at site',
      qty: '8',
      delivery_date: '2026-09-20',
      verb: 'CANCEL_BALANCE',
      state: 'cancelled',
      line_cancelled: true,
      ackState: 'acknowledged',
    }),
  ],
  'oih-2': [
    buildLine('oih-2', {
      item_code: 'GLS-PNL-08',
      product_name: 'Tempered Glass Panel 8mm',
      qty: '55',
      delivery_date: '2026-10-10',
      supplier: 'Kencana Glassworks',
      location: 'JB-WH02',
      verb: 'ORDER',
      ackState: 'awaiting',
    }),
    buildLine('oih-2', {
      item_code: 'ALM-FRM-30',
      product_name: 'Aluminium Window Frame 30mm',
      qty: '32',
      delivery_date: '2026-10-12',
      supplier: 'Kencana Glassworks',
      location: 'JB-WH02',
      verb: 'ORDER',
      ackState: 'acknowledged',
      links: [
        { id: 'oih-2-link-1', kind: 'po', document: '202609-S0060', qty: '32', po_id: 'po-3' },
      ],
    }),
    buildLine('oih-2', {
      item_code: 'SLT-RUB-01',
      product_name: 'Rubber Weather Seal',
      qty: '90',
      delivery_date: '2026-10-12',
      supplier: 'Kencana Glassworks',
      location: 'JB-WH02',
      verb: 'ORDER',
      ackState: 'acknowledged',
      links: [
        { id: 'oih-2-link-2', kind: 'po', document: '202609-S0060', qty: '90', po_id: 'po-3' },
      ],
    }),
    buildLine('oih-2', {
      item_code: 'HNG-STL-02',
      product_name: 'Stainless Steel Hinge',
      qty: '48',
      delivery_date: '2026-10-15',
      verb: 'CANCEL_BALANCE',
      state: 'cancelled',
      line_cancelled: true,
      ackState: 'acknowledged',
    }),
  ],
  'oih-3': [
    buildLine('oih-3', {
      item_code: 'WD-FLR-12',
      product_name: 'Engineered Wood Flooring 12mm',
      qty: '210',
      delivery_date: '2026-09-22',
      supplier: 'Menara Timber Supplies',
      location: 'KL-WH03',
      verb: 'ORDER',
      ackState: 'acknowledged',
      links: [
        { id: 'oih-3-link-1', kind: 'po', document: '202609-S0033', qty: '210', po_id: 'po-4' },
      ],
    }),
    buildLine('oih-3', {
      item_code: 'SKR-BRD-06',
      product_name: 'Skirting Board 06',
      qty: '75',
      delivery_date: '2026-09-22',
      supplier: 'Menara Timber Supplies',
      location: 'KL-WH03',
      verb: 'ORDER',
      ackState: 'acknowledged',
      links: [
        { id: 'oih-3-link-2', kind: 'spo', document: 'SPO-2026/09-0020', qty: '75' },
      ],
    }),
  ],
  'oih-4': [
    buildLine('oih-4', {
      item_code: 'LGT-LED-40',
      product_name: 'LED Panel Light 40W',
      qty: '16',
      delivery_date: '2026-09-18',
      verb: 'CANCEL_BALANCE',
      state: 'cancelled',
      line_cancelled: true,
      ackState: 'acknowledged',
    }),
    buildLine('oih-4', {
      item_code: 'SWT-DBL-02',
      product_name: 'Double Gang Switch',
      qty: '24',
      delivery_date: '2026-09-18',
      verb: 'CANCEL_BALANCE',
      state: 'cancelled',
      line_cancelled: true,
      ackState: 'acknowledged',
    }),
  ],
  // AC-DT-03 / owner facts: zero linked documents anywhere on this header.
  'oih-5': [
    buildLine('oih-5', {
      item_code: 'STL-BM-200',
      product_name: 'Structural Steel Beam 200mm',
      qty: '12',
      delivery_date: '2026-10-01',
      verb: 'ORDER',
      ackState: 'awaiting',
    }),
    buildLine('oih-5', {
      item_code: 'BLT-M12',
      product_name: 'M12 Structural Bolt',
      qty: '480',
      delivery_date: '2026-10-01',
      verb: 'ORDER',
      ackState: 'acknowledged',
    }),
    buildLine('oih-5', {
      item_code: 'PNT-PRM-05',
      product_name: 'Anti-rust Primer, 5L',
      qty: '20',
      delivery_date: '2026-10-03',
      verb: 'ORDER',
      ackState: 'acknowledged',
    }),
  ],
  // AC-DP-03 / plan facts: 40+ lines, to exercise the Lines tab's own pagination.
  'oih-6': Array.from({ length: 42 }, (_, index) =>
    buildLine('oih-6', {
      item_code: `UBP-${String(index + 1).padStart(3, '0')}`,
      product_name: `Utama Builders Part ${index + 1}`,
      qty: String(5 + (index % 6) * 3),
      delivery_date: index % 3 === 0 ? '2026-10-04' : '2026-10-11',
      supplier: 'Damansara Supply Co',
      location: 'SEL-WH04',
      verb: index % 7 === 0 ? 'ORDER_BACK' : 'ORDER',
      ackState: index % 5 === 0 ? 'awaiting' : 'acknowledged',
      links:
        index % 5 === 0
          ? []
          : [
              {
                id: `oih-6-link-${index}`,
                kind: 'po',
                document: '202609-S0071',
                qty: String(5 + (index % 6) * 3),
                po_id: 'po-5',
              },
            ],
    }),
  ),
  'oih-7': [
    buildLine('oih-7', {
      item_code: 'PVC-PIP-50',
      product_name: 'PVC Pipe 50mm',
      qty: '60',
      delivery_date: '2026-09-19',
      verb: 'ORDER',
      ackState: 'acknowledged',
      links: [
        { id: 'oih-7-link-1', kind: 'po', document: '202609-S0028', qty: '60', po_id: 'po-6' },
      ],
    }),
    buildLine('oih-7', {
      item_code: 'ELB-90-50',
      product_name: 'PVC Elbow 90deg 50mm',
      qty: '24',
      delivery_date: '2026-09-19',
      verb: 'ORDER',
      ackState: 'acknowledged',
      links: [
        { id: 'oih-7-link-2', kind: 'po', document: '202609-S0028', qty: '24', po_id: 'po-6' },
      ],
    }),
  ],
};

const RELATED_DOCUMENTS: Record<string, OrderInquiryHeaderRelatedDocuments> = {
  'oih-1': {
    purchase_orders: [
      {
        po_id: 'po-1',
        po_number: '202609-S0041',
        supplier_name: 'Sunrise Ceramics Sdn Bhd',
        po_date: '2026-09-09',
        lines_linked: 2,
        qty_linked: '518',
      },
      {
        po_id: 'po-2',
        po_number: '202609-S0055',
        supplier_name: 'Metroline Hardware',
        po_date: '2026-09-11',
        lines_linked: 1,
        qty_linked: '30',
      },
    ],
    spos: [
      { spo_number: 'SPO-2026/09-0012', supplier_name: 'Metroline Hardware', lines_linked: 1, qty_linked: '24' },
    ],
  },
  'oih-2': {
    purchase_orders: [
      {
        po_id: 'po-3',
        po_number: '202609-S0060',
        supplier_name: 'Kencana Glassworks',
        po_date: '2026-09-10',
        lines_linked: 2,
        qty_linked: '122',
      },
    ],
    spos: [],
  },
  'oih-3': {
    purchase_orders: [
      {
        po_id: 'po-4',
        po_number: '202609-S0033',
        supplier_name: 'Menara Timber Supplies',
        po_date: '2026-09-09',
        lines_linked: 1,
        qty_linked: '210',
      },
    ],
    spos: [
      { spo_number: 'SPO-2026/09-0020', supplier_name: 'Menara Timber Supplies', lines_linked: 1, qty_linked: '75' },
    ],
  },
  'oih-4': { purchase_orders: [], spos: [] },
  'oih-5': { purchase_orders: [], spos: [] },
  'oih-6': {
    purchase_orders: [
      {
        po_id: 'po-5',
        po_number: '202609-S0071',
        supplier_name: 'Damansara Supply Co',
        po_date: '2026-09-12',
        lines_linked: 34,
        qty_linked: '374',
      },
    ],
    spos: [],
  },
  'oih-7': {
    purchase_orders: [
      {
        po_id: 'po-6',
        po_number: '202609-S0028',
        supplier_name: 'PipeCo Trading',
        po_date: '2026-09-13',
        lines_linked: 2,
        qty_linked: '84',
      },
    ],
    spos: [],
  },
};

/** Non-cancelled rows only (AC-LS-05); `lines_to_confirm` counts `awaiting`/`changed`. */
function totalsOf(lines: OrderInquiryWorklistRow[]) {
  const active = lines.filter((line) => line.state !== 'cancelled');
  const toConfirm = active.filter(
    (line) => line.ack_state === 'awaiting' || line.ack_state === 'changed',
  ).length;
  const qty = active.reduce((sum, line) => sum + Number(line.qty || '0'), 0);
  return {
    lines_total: active.length,
    lines_to_confirm: toConfirm,
    qty_total: String(qty),
  };
}

function toHeader(seed: MockHeaderSeed): OrderInquiryHeader {
  const totals = totalsOf(LINES_BY_HEADER[seed.id] ?? []);
  return {
    id: seed.id,
    inquiry_no: seed.inquiry_no,
    legacy_inquiry_no: seed.legacy_inquiry_no ?? null,
    raised_at: seed.raised_at,
    raised_by_name: seed.raised_by_name,
    sales_order_id: seed.sales_order_id,
    project_sales_order_id: seed.project_sales_order_id,
    so_number: seed.so_number,
    so_date: seed.so_date,
    customer_name: seed.customer_name,
    customer_code: seed.customer_code,
    project_id: seed.project_id,
    project_title: seed.project_title,
    agent_name: seed.agent_name,
    ...totals,
    status: totals.lines_to_confirm > 0 ? 'outstanding' : 'completed',
  };
}

const HEADERS: OrderInquiryHeader[] = HEADER_SEEDS.map(toHeader);

function seedOf(id: string): MockHeaderSeed | undefined {
  return HEADER_SEEDS.find((seed) => seed.id === id);
}

function matchesQuery(header: OrderInquiryHeader, needle: string): boolean {
  const haystacks = [
    header.inquiry_no,
    header.legacy_inquiry_no,
    header.so_number,
    header.customer_name,
    header.project_title,
    header.agent_name,
    // Search also reaches inside the OI's own lines (plan S2/AC-LS-04).
    ...(LINES_BY_HEADER[header.id] ?? []).flatMap((line) => [line.item_code, line.location]),
  ];
  return haystacks.some((value) => (value ?? '').toLowerCase().includes(needle));
}

const SORTERS: Record<string, (header: OrderInquiryHeader) => string | number> = {
  raised_at: (h) => h.raised_at ?? '',
  inquiry_no: (h) => h.inquiry_no,
  so_number: (h) => h.so_number ?? '',
  raised_by: (h) => h.raised_by_name ?? '',
  lines_total: (h) => h.lines_total,
  qty_total: (h) => Number(h.qty_total || '0'),
  customer: (h) => h.customer_name ?? '',
  project: (h) => h.project_title ?? '',
  agent: (h) => h.agent_name ?? '',
  so_date: (h) => h.so_date ?? '',
  status: (h) => h.status,
};

export function mockListOrderInquiryHeaders(params: OrderInquiryHeaderListParams): {
  data: OrderInquiryHeader[];
  total: number;
  page: number;
  limit: number;
} {
  const state = params.state ?? 'outstanding';
  let rows = HEADERS.filter((header) => state === 'all' || header.status === state);

  const needle = (params.query ?? '').trim().toLowerCase();
  if (needle) rows = rows.filter((header) => matchesQuery(header, needle));

  if (params.raised_by) {
    rows = rows.filter((header) => header.raised_by_name === params.raised_by);
  }
  if (params.agent) {
    rows = rows.filter((header) => header.agent_name === params.agent);
  }
  if (params.project_id) {
    rows = rows.filter((header) => header.project_id === params.project_id);
  }

  const sortKey = SORTERS[params.sort ?? 'raised_at'] ?? SORTERS.raised_at;
  const dir = params.dir === 'desc' ? -1 : 1;
  rows = [...rows].sort((a, b) => {
    const av = sortKey(a);
    const bv = sortKey(b);
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    // Stable tiebreak so equal keys never reorder between renders (AC-LS-03).
    return a.id.localeCompare(b.id) * dir;
  });

  const page = params.page ?? 1;
  const limit = params.limit ?? 25;
  const start = (page - 1) * limit;
  return { data: rows.slice(start, start + limit), total: rows.length, page, limit };
}

export function mockGetOrderInquiryHeader(id: string): OrderInquiryHeaderDetail | null {
  const seed = seedOf(id);
  const header = HEADERS.find((h) => h.id === id);
  if (!seed || !header) return null;
  return { ...header, order_type: seed.order_type ?? null, raise_history: seed.raise_history };
}

export function mockGetOrderInquiryHeaderLines(id: string): OrderInquiryWorklistRow[] {
  return LINES_BY_HEADER[id] ?? [];
}

export function mockGetOrderInquiryHeaderRelatedDocuments(
  id: string,
): OrderInquiryHeaderRelatedDocuments {
  return RELATED_DOCUMENTS[id] ?? { purchase_orders: [], spos: [] };
}

/** The Raised by / Agent / Project filter options (AC-HL-05), off the fixture itself so
 * they can never name a value the list does not actually hold. */
export function mockOrderInquiryHeaderFilterOptions() {
  const distinct = <T,>(values: (T | null | undefined)[]): T[] =>
    Array.from(new Set(values.filter((v): v is T => v !== null && v !== undefined)));

  return {
    raisedBy: distinct(HEADERS.map((h) => h.raised_by_name)).map((name) => ({
      value: name,
      label: name,
    })),
    agents: distinct(HEADERS.map((h) => h.agent_name)).map((name) => ({
      value: name,
      label: name,
    })),
    projects: distinct(HEADERS.map((h) => (h.project_id ? h.project_id : null))).map((id) => ({
      value: id,
      label: HEADERS.find((h) => h.project_id === id)?.project_title ?? id,
    })),
  };
}

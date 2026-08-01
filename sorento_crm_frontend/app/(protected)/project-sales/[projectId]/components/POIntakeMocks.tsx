'use client';

/**
 * Toggleable fixtures for the PO confirm screen, so every state can be looked at while the
 * backend for this contract is still being written.
 *
 * Reach them by adding `?po_mock=<scenario>` to the confirm URL. Nothing here runs unless
 * that parameter is present: the page calls the live controller and the mock controller side
 * by side (hooks must be unconditional) and picks one.
 *
 * The numbers are the real project's numbers where the contract quotes them: PO
 * `HQ/26/01/041`, filing reference `PS26-0143`, 10 pages, 52 lines, `SRTWC8613-RL` 927 SETS
 * at 392.85, total 1,810,640.62, a strike-through cancelling line 7 and a pencil note
 * naming successor PO `HQ/26/05/087`.
 */
import * as React from 'react';
import { toast } from 'sonner';
import type {
  POAnnotation,
  POAnnotationEditBody,
  POIntakeController,
  POLineUpdateBody,
  POVersion,
  POVersionLine,
} from '../../_shared/types/poIntake.types';
import { resolveExtractionPhase } from '../../_shared/types/poIntake.types';
import { multiplyMoney, sumMoney } from './POIntakeMoney';

export const PO_MOCK_PARAM = 'po_mock';

export type POMockScenario =
  | 'queued'
  | 'running'
  | 'done'
  | 'mismatch'
  | 'partial'
  | 'failed'
  | 'empty'
  | 'reviewed'
  | 'confirmed'
  | 'approved';

const SCENARIOS: POMockScenario[] = [
  'queued',
  'running',
  'done',
  'mismatch',
  'partial',
  'failed',
  'empty',
  'reviewed',
  'confirmed',
  'approved',
];

export function isPOMockScenario(value: string | null): value is POMockScenario {
  return Boolean(value) && SCENARIOS.includes(value as POMockScenario);
}

/** One product per PO line family, in the shapes this client's documents actually use. */
const CATALOGUE: Array<{
  code: string;
  name: string;
  price: string;
  uom: string;
}> = [
  {
    code: 'SRTWC8613-RL',
    name: 'RIMLESS CLOSE COUPLED WC, S-TRAP 250MM',
    price: '392.85',
    uom: 'SETS',
  },
  {
    code: 'SRTWC8620-RL',
    name: 'RIMLESS WALL HUNG WC WITH CONCEALED CISTERN',
    price: '615.40',
    uom: 'SETS',
  },
  {
    code: 'SRTBS2100',
    name: 'COUNTER TOP BASIN 500MM WHITE',
    price: '148.00',
    uom: 'NOS',
  },
  {
    code: 'SRTBS2140-PD',
    name: 'PEDESTAL BASIN 560MM WHITE',
    price: '206.75',
    uom: 'NOS',
  },
  {
    code: 'SRTMX3300-CP',
    name: 'BASIN PILLAR TAP CHROME',
    price: '96.30',
    uom: 'NOS',
  },
  {
    code: 'SRTMX3380-CP',
    name: 'SHOWER MIXER WITH HAND SHOWER SET',
    price: '284.15',
    uom: 'SETS',
  },
  {
    code: 'SRTSK5501-SS',
    name: 'KITCHEN SINK SINGLE BOWL STAINLESS STEEL',
    price: '331.00',
    uom: 'NOS',
  },
  {
    code: 'SRTSK5590-CP',
    name: 'KITCHEN SINK MIXER PULL OUT',
    price: '412.60',
    uom: 'NOS',
  },
  {
    code: 'SRTFV1001',
    name: 'FLOOR TRAP 100MM X 100MM STAINLESS',
    price: '37.50',
    uom: 'NOS',
  },
  {
    code: 'SRTFV1002',
    name: 'BOTTLE TRAP WITH FLEXIBLE PIPE',
    price: '42.80',
    uom: 'NOS',
  },
  {
    code: 'SRTAC7700',
    name: 'TOILET PAPER HOLDER CHROME',
    price: '58.90',
    uom: 'NOS',
  },
  {
    code: 'SRTAC7740',
    name: 'DOUBLE ROBE HOOK CHROME',
    price: '31.25',
    uom: 'NOS',
  },
  {
    code: 'SRTSH6600-CP',
    name: 'RAIN SHOWER HEAD 250MM SQUARE',
    price: '268.00',
    uom: 'NOS',
  },
  {
    code: 'B2155-NL-BLUE',
    name: 'MOSAIC BORDER TILE 300X300 BLUE',
    price: '74.15',
    uom: 'BOX',
  },
];

/** Deterministic, so two people looking at the mock see the same paper. */
const QUANTITIES = [927, 894, 16, 9, 132, 48, 216, 60, 24, 12, 36, 18, 6, 4];

function buildLines(count: number): POVersionLine[] {
  const lines: POVersionLine[] = [];
  for (let index = 0; index < count; index += 1) {
    const item = CATALOGUE[index % CATALOGUE.length];
    const qty = String(QUANTITIES[index % QUANTITIES.length]);
    const amount = multiplyMoney(qty, item.price) ?? '0.00';
    lines.push({
      id: `mock-line-${index + 1}`,
      line_no: index + 1,
      stock_code_raw: item.code,
      description_raw: item.name,
      qty,
      uom_raw: item.uom,
      unit_price: item.price,
      amount,
      arithmetic_ok: true,
      is_cancelled: false,
      resolved_product_id:
        index % 7 === 3 ? null : `mock-product-${index % CATALOGUE.length}`,
      resolved_product_code: index % 7 === 3 ? null : item.code,
      resolution_source: index % 7 === 3 ? null : index % 5 === 0 ? 'map' : 'code',
      // Ten pages, 52 lines: roughly six lines to a page, which is what the scan looks like.
      page_no: Math.min(10, Math.floor(index / 6) + 1),
    });
  }
  return lines;
}

/** A pencil crop we do not have a real image for. Shows the card layout, not the paper. */
function cropPlaceholder(text: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="420" height="96"><rect width="420" height="96" fill="#fdfbf4"/><text x="14" y="56" font-family="Comic Sans MS, cursive" font-size="20" fill="#1f3f8f">${text}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function annotations(): POAnnotation[] {
  return [
    {
      id: 'mock-annot-1',
      page_no: 4,
      crop_url: cropPlaceholder('cancel item (7) refer to new P/O HQ/26/05/087'),
      raw_text: 'cancel item (7) due to changed the price, refer to new P/O HQ/26/05/087',
      written_date: '15/5/26',
      refers_to_lines: [7],
      interpretation: 'cancel_line',
      interpretation_json: { line_nos: [7], reason: 'price changed' },
      state: 'proposed',
      actioned_by_name: null,
      actioned_at: null,
      action_note: null,
    },
    {
      id: 'mock-annot-2',
      page_no: 4,
      crop_url: cropPlaceholder('refer to new P/O HQ/26/05/087'),
      raw_text: 'refer to new P/O HQ/26/05/087',
      written_date: '15/5/26',
      refers_to_lines: [],
      interpretation: 'successor_po',
      interpretation_json: { po_number: 'HQ/26/05/087' },
      state: 'proposed',
      actioned_by_name: null,
      actioned_at: null,
      action_note: null,
    },
    {
      id: 'mock-annot-3',
      page_no: 2,
      crop_url: cropPlaceholder('amend code and description for item (5), (20), (23)'),
      raw_text: 'amend code and description for item (5), (20), (23)',
      written_date: '26/1/26',
      refers_to_lines: [5, 20, 23],
      interpretation: 'amend_code',
      interpretation_json: { line_nos: [5, 20, 23], code: 'SRTMX3300-BK' },
      state: 'proposed',
      actioned_by_name: null,
      actioned_at: null,
      action_note: null,
    },
    {
      id: 'mock-annot-4',
      page_no: 10,
      crop_url: null,
      raw_text: 'Approved - Yana 19/1/26',
      written_date: '19/1/26',
      refers_to_lines: [],
      interpretation: 'signature',
      interpretation_json: null,
      state: 'proposed',
      actioned_by_name: null,
      actioned_at: null,
      action_note: null,
    },
  ];
}

function baseVersion(lines: POVersionLine[]): POVersion {
  const linesTotal =
    sumMoney(lines.filter((line) => !line.is_cancelled).map((l) => l.amount)) ?? '0.00';
  return {
    id: 'mock-version',
    purchase_order_id: 'mock-po',
    version_no: 1,
    extraction_state: 'done',
    extraction_error: null,
    extraction_model: 'gemini-2.5-flash',
    page_count: 10,
    document_url: null,
    header: {
      po_number: 'HQ/26/01/041',
      po_date: '2026-01-19',
      term_days: 60,
      sales_person: 'Ali Hassan',
      customer_order_ref: 'BUI/TR/2026/0114',
      admin_ref: 'PS26-0143',
      remark:
        'Delivery to site as per attached schedule. Contact site PIC before dispatch.',
    },
    totals: {
      extracted_total: linesTotal,
      lines_total: linesTotal,
      arithmetic_passed: lines.length,
      arithmetic_total: lines.length,
    },
    lines,
    annotations: annotations(),
    confirmed_at: null,
    pages_extracted: 10,
    failed_pages: [],
    purchase_order: {
      po_number: 'HQ/26/01/041',
      status: 'draft',
      approved_by_name: null,
      approved_at: null,
      countersigned_by_name: null,
      countersigned_at: null,
    },
  };
}

export function mockVersion(scenario: POMockScenario): POVersion {
  if (scenario === 'queued' || scenario === 'running' || scenario === 'failed') {
    const shell = baseVersion([]);
    return {
      ...shell,
      extraction_state: scenario === 'failed' ? 'failed' : scenario,
      extraction_error:
        scenario === 'failed'
          ? 'The document could not be read. Page 1 came back blank at 300 dpi.'
          : null,
      pages_extracted: null,
      totals: {
        extracted_total: null,
        lines_total: '0.00',
        arithmetic_passed: 0,
        arithmetic_total: 0,
      },
      annotations: [],
    };
  }

  if (scenario === 'empty') {
    const shell = baseVersion([]);
    return {
      ...shell,
      totals: {
        extracted_total: null,
        lines_total: '0.00',
        arithmetic_passed: 0,
        arithmetic_total: 0,
      },
      annotations: [],
    };
  }

  if (scenario === 'partial') {
    // Seven pages read, three not. The lines that exist are fine; the sum is far below the
    // total printed on the paper, which is exactly how a short read announces itself.
    const lines = buildLines(52).filter((line) => (line.page_no ?? 1) <= 7);
    const shell = baseVersion(lines);
    return {
      ...shell,
      extraction_error: 'Pages 8, 9 and 10 could not be read (scan too dark).',
      pages_extracted: 7,
      failed_pages: [8, 9, 10],
      totals: {
        ...shell.totals,
        extracted_total: '1810640.62',
      },
      annotations: annotations().filter((note) => note.page_no <= 7),
    };
  }

  if (scenario === 'mismatch') {
    const lines = buildLines(52);
    // One misread amount, which is what a total difference is usually made of.
    lines[13] = { ...lines[13], amount: '3410.00', arithmetic_ok: false };
    const shell = baseVersion(lines);
    const printed = sumMoney(buildLines(52).map((line) => line.amount)) ?? '0.00';
    return {
      ...shell,
      totals: {
        extracted_total: printed,
        lines_total: sumMoney(lines.map((line) => line.amount)) ?? '0.00',
        arithmetic_passed: 51,
        arithmetic_total: 52,
      },
    };
  }

  const lines = buildLines(52);
  const shell = baseVersion(lines);

  if (scenario === 'done') return shell;

  const reviewed: POVersion = {
    ...shell,
    annotations: shell.annotations.map((note, index) => ({
      ...note,
      state: index === 3 ? 'rejected' : index === 2 ? 'edited' : 'accepted',
      actioned_by_name: 'Yana Abdullah',
      actioned_at: '2026-05-15T02:41:00',
      action_note:
        index === 3 ? 'This is the approval signature, not an amendment.' : null,
    })),
  };

  if (scenario === 'reviewed') return reviewed;

  const confirmed: POVersion = {
    ...reviewed,
    confirmed_at: '2026-05-15T03:02:00',
    confirmed_by_name: 'Yana Abdullah',
  };

  if (scenario === 'confirmed') return confirmed;

  return {
    ...confirmed,
    purchase_order: {
      po_number: 'HQ/26/01/041',
      status: 'approved',
      approved_by_name: 'Yana Abdullah',
      approved_at: '2026-05-15T03:05:00',
      countersigned_by_name: null,
      countersigned_at: null,
    },
  };
}

/**
 * The mock controller. Same shape as the live one, and it APPLIES what a card says locally
 * so the accept / edit / reject flow can be seen doing the thing it claims to do.
 */
export function usePOIntakeMockController(
  scenario: POMockScenario | null,
): POIntakeController {
  const [version, setVersion] = React.useState<POVersion | null>(() =>
    scenario ? mockVersion(scenario) : null,
  );

  React.useEffect(() => {
    setVersion(scenario ? mockVersion(scenario) : null);
  }, [scenario]);

  const recount = React.useCallback((next: POVersion): POVersion => {
    const active = next.lines.filter((line) => !line.is_cancelled);
    return {
      ...next,
      totals: {
        ...next.totals,
        lines_total:
          sumMoney(active.map((line) => line.amount)) ?? next.totals.lines_total,
        arithmetic_passed: next.lines.filter((line) => line.arithmetic_ok).length,
        arithmetic_total: next.lines.length,
      },
    };
  }, []);

  const applyToLines = React.useCallback(
    (
      current: POVersion,
      lineNos: number[],
      change: (line: POVersionLine) => POVersionLine,
    ): POVersion =>
      recount({
        ...current,
        lines: current.lines.map((line) =>
          lineNos.includes(line.line_no) ? change(line) : line,
        ),
      }),
    [recount],
  );

  const actOnAnnotation = React.useCallback(
    (
      annotationId: string,
      state: POAnnotation['state'],
      note: string | null,
      override?: POAnnotationEditBody,
    ) => {
      setVersion((current) => {
        if (!current) return current;
        const annotation = current.annotations.find((item) => item.id === annotationId);
        if (!annotation) return current;
        const interpretation = override?.interpretation ?? annotation.interpretation;
        const json =
          override?.interpretation_json ?? annotation.interpretation_json ?? {};
        const lineNos = Array.isArray((json as { line_nos?: number[] }).line_nos)
          ? ((json as { line_nos?: number[] }).line_nos as number[])
          : annotation.refers_to_lines;

        let next: POVersion = {
          ...current,
          annotations: current.annotations.map((item) =>
            item.id === annotationId
              ? {
                  ...item,
                  interpretation,
                  interpretation_json: json,
                  state,
                  actioned_by_name: 'You',
                  actioned_at: new Date().toISOString().slice(0, 19),
                  action_note: note,
                }
              : item,
          ),
        };

        if (state !== 'rejected') {
          if (interpretation === 'cancel_line') {
            next = applyToLines(next, lineNos, (line) => ({
              ...line,
              is_cancelled: true,
            }));
          } else if (interpretation === 'amend_code') {
            const code = String((json as { code?: string }).code ?? '');
            if (code) {
              next = applyToLines(next, lineNos, (line) => ({
                ...line,
                stock_code_raw: code,
              }));
            }
          } else if (interpretation === 'amend_description') {
            const description = String(
              (json as { description?: string }).description ?? '',
            );
            if (description) {
              next = applyToLines(next, lineNos, (line) => ({
                ...line,
                description_raw: description,
              }));
            }
          }
        }
        return recount(next);
      });
    },
    [applyToLines, recount],
  );

  const updateLine = React.useCallback(
    async (lineId: string, body: POLineUpdateBody) => {
      setVersion((current) => {
        if (!current) return current;
        const next = {
          ...current,
          lines: current.lines.map((line) => {
            if (line.id !== lineId) return line;
            const merged: POVersionLine = {
              ...line,
              ...(body.stock_code_raw !== undefined
                ? { stock_code_raw: body.stock_code_raw }
                : {}),
              ...(body.description_raw !== undefined
                ? { description_raw: body.description_raw }
                : {}),
              ...(body.qty !== undefined ? { qty: body.qty } : {}),
              ...(body.uom_raw !== undefined ? { uom_raw: body.uom_raw } : {}),
              ...(body.unit_price !== undefined ? { unit_price: body.unit_price } : {}),
              ...(body.amount !== undefined ? { amount: body.amount } : {}),
              ...(body.is_cancelled !== undefined
                ? { is_cancelled: body.is_cancelled }
                : {}),
              ...(body.resolved_product_id !== undefined
                ? {
                    resolved_product_id: body.resolved_product_id,
                    resolution_source: body.resolved_product_id
                      ? ('manual' as const)
                      : null,
                  }
                : {}),
            };
            const expected = multiplyMoney(merged.qty, merged.unit_price);
            return {
              ...merged,
              arithmetic_ok: expected !== null && expected === merged.amount,
            };
          }),
        };
        return recount(next);
      });
    },
    [recount],
  );

  return {
    version,
    phase: resolveExtractionPhase(version),
    isLoading: false,
    isError: false,
    error: null,
    isPolling:
      version?.extraction_state === 'queued' || version?.extraction_state === 'running',
    savingLineIds: [],
    savingAnnotationIds: [],
    isConfirming: false,
    isStamping: false,
    isSavingHeader: false,
    updateHeader: async (body) => {
      setVersion((current) =>
        current ? { ...current, header: { ...current.header, ...body } } : current,
      );
    },
    updateLine,
    confirm: async () => {
      setVersion((current) =>
        current
          ? {
              ...current,
              confirmed_at: new Date().toISOString().slice(0, 19),
              confirmed_by_name: 'You',
            }
          : current,
      );
      toast.success('Confirmed in this sample. Nothing was sent to the server.');
    },
    acceptAnnotation: async (annotationId, note) => {
      actOnAnnotation(annotationId, 'accepted', note ?? null);
    },
    editAnnotation: async (annotationId, body) => {
      actOnAnnotation(annotationId, 'edited', body.note ?? null, body);
    },
    rejectAnnotation: async (annotationId, note) => {
      actOnAnnotation(annotationId, 'rejected', note);
    },
    approve: async () => {
      setVersion((current) =>
        current
          ? {
              ...current,
              purchase_order: {
                ...(current.purchase_order ?? {}),
                status: 'approved',
                approved_by_name: 'You',
                approved_at: new Date().toISOString().slice(0, 19),
              },
            }
          : current,
      );
    },
    countersign: async () => {
      setVersion((current) =>
        current
          ? {
              ...current,
              purchase_order: {
                ...(current.purchase_order ?? {}),
                countersigned_by_name: 'Baser Ismail',
                countersigned_at: new Date().toISOString().slice(0, 19),
              },
            }
          : current,
      );
    },
    isMock: true,
  };
}

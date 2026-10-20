/**
 * OI-LINE-SPLIT v4 test kit: payload builders, a dialog renderer and the DOM-contract
 * lookups (`PLAN-oi-line-split-16oct.md` "Build v4" DOM contract) shared by the sheet specs
 * `LineSplitDialog.sheet*.test.tsx` and `LineSplitDialog.drag*.test.tsx`.
 *
 * The service module is mocked in each spec (vi.mock is per file); this file only builds
 * data and drives the rendered dialog.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, within } from '@testing-library/react';

export const PSO = 'pso-417636';

export interface WireSplit {
  id: string;
  qty: number;
  delivery_date: string | null;
  is_cancel: boolean;
  sits_on_line_id: string | null;
  remark: string;
  /** Round 3: the text Confirm would write when `remark` is empty. */
  remark_generated: string;
}

export interface WireLine {
  line_id: string;
  line_no: number;
  item_code: string;
  location: string;
  base_qty: number;
  base_date: string | null;
  now_qty: number;
  now_date: string | null;
  pending_change: boolean;
  new_qty: number | null;
  new_date: string | null;
  delivered_qty: number;
  split_state: 'acting' | 'applied' | 'stale';
  acting: boolean;
  /** Round 3: qty of the extra row AutoCount added beyond the base; null = none. */
  extra_qty: number | null;
  extra_remark: string | null;
  /** Round 3: generated text for the line's own row. */
  remark_generated: string;
  splits: WireSplit[];
}

export function wireLine(
  no: number,
  item: string,
  baseQty: number,
  baseDate: string | null,
  opts: Partial<WireLine> = {},
): WireLine {
  return {
    line_id: `L${no}`,
    line_no: no,
    item_code: item,
    location: 'BRW-BB',
    base_qty: baseQty,
    base_date: baseDate,
    now_qty: baseQty,
    now_date: baseDate,
    pending_change: false,
    new_qty: null,
    new_date: null,
    delivered_qty: 0,
    split_state: 'acting',
    acting: true,
    extra_qty: null,
    extra_remark: null,
    remark_generated: '',
    splits: [],
    ...opts,
  };
}

export function wireSplit(
  id: string,
  qty: number,
  date: string | null,
  on: string | null,
  extra: Partial<WireSplit> = {},
): WireSplit {
  return {
    id,
    qty,
    delivery_date: date,
    is_cancel: false,
    sits_on_line_id: on,
    remark: '',
    remark_generated: '',
    ...extra,
  };
}

/**
 * SO417636, unsplit, in a deliberately unsorted server order. Sorted by the sheet:
 * L768 (CSK11A), L480, L608, L752 (CSK14B at BRW-BB), L900 (CSK14B at KL-HQ).
 * L752 carries a pending AutoCount change 504 @ 20/12/2026 -> 649 @ 02/01/2027.
 */
export function ownerCase() {
  return {
    pso_id: PSO,
    so_number: 'SO417636',
    so_date: '2026-09-03',
    customer: 'GLOBAL INGRESS SDN BHD (PROJECT)',
    project: '405U + 397U PANGSAPURI',
    lines: [
      wireLine(768, 'CSK11A', 335, '2027-01-02'),
      wireLine(752, 'CSK14B', 504, '2026-12-20', {
        now_qty: 649,
        now_date: '2027-01-02',
        pending_change: true,
        new_qty: 649,
        new_date: '2027-01-02',
      }),
      wireLine(608, 'CSK14B', 192, '2026-11-20'),
      wireLine(480, 'CSK14B', 417, '2026-10-20'),
      wireLine(900, 'CSK14B', 50, '2026-10-01', { location: 'KL-HQ' }),
    ],
  };
}

/** The owner's finished plan saved: 480 = 14 own + 236 on 608 + 167 on a new line. */
export function savedCase() {
  const p = ownerCase();
  const l480 = p.lines.find((l) => l.line_id === 'L480')!;
  l480.splits = [
    wireSplit('s14', 14, '2026-09-20', 'L480', { remark: 'Under pre-order' }),
    wireSplit('s236', 236, '2026-11-20', 'L608'),
    wireSplit('s167', 167, '2029-11-20', null, { remark: 'Order' }),
  ];
  return p;
}

/** SO424910: line 16 76 -> 2 with 4 moved onto added line 32; line 32 added by AutoCount. */
export function addedCase() {
  return {
    pso_id: 'pso-424910',
    so_number: 'SO424910',
    so_date: '2026-10-01',
    customer: 'C',
    project: 'P',
    lines: [
      wireLine(16, 'SRTSP124', 76, '2026-10-07', {
        now_qty: 2,
        pending_change: true,
        splits: [
          wireSplit('a', 2, '2026-10-07', 'L16'),
          wireSplit('b', 4, '2026-10-16', 'L32'),
          wireSplit('d', 70, null, 'L16', { is_cancel: true }),
        ],
      }),
      wireLine(32, 'SRTSP124', 0, null, {
        now_qty: 4,
        now_date: '2026-10-16',
        pending_change: true,
        new_qty: 4,
        new_date: '2026-10-16',
      }),
    ],
  };
}

type DialogProps = {
  open: boolean;
  psoId: string;
  focusLineId?: string;
  onOpenChange: (open: boolean) => void;
};

export async function renderDialog(
  props: Partial<DialogProps> = {},
  psoId: string = PSO,
) {
  const mod = (await import(
    '@/app/(protected)/project-sales/fulfilment-planning/components/LineSplitDialog'
  )) as unknown as { LineSplitDialog: React.ComponentType<DialogProps> };
  const onOpenChange = props.onOpenChange ?? (() => undefined);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={client}>
      <mod.LineSplitDialog
        open
        psoId={psoId}
        focusLineId={props.focusLineId ?? 'L480'}
        {...props}
        onOpenChange={onOpenChange}
      />
    </QueryClientProvider>,
  );
  return utils;
}

/** Wait for the sheet table to be on screen. */
export const sheet = () => screen.findByRole('table', { name: 'Split delivery sheet' });
export const block = (no: number) => screen.getByTestId(`split-line-${no}`);
export const blockIds = () =>
  screen.getAllByTestId(/^split-line-/).map((el) => el.getAttribute('data-testid'));

export const qty = (no: number, n: number) =>
  screen.getByLabelText(`Quantity, line ${no} split ${n}`) as HTMLInputElement;
export const dateIn = (no: number, n: number) =>
  screen.getByLabelText(`Date, line ${no} split ${n}`) as HTMLInputElement;
export const remarkIn = (no: number, n: number) =>
  screen.getByLabelText(`Remark, line ${no} split ${n}`) as HTMLInputElement;
export const queryQty = (no: number, n: number) =>
  screen.queryByLabelText(`Quantity, line ${no} split ${n}`);
export const remainQty = (no: number) =>
  screen.getByRole('button', { name: `Split line ${no} quantity` });
export const remainDate = (no: number) =>
  screen.getByRole('button', { name: `Split line ${no} date` });
export const addBtn = (no: number) =>
  screen.getByRole('button', { name: `Add a split to line ${no}` });
export const removeBtn = (no: number, n: number) =>
  screen.getByRole('button', { name: `Remove split ${n} of line ${no}` });
export const balance = (no: number) => screen.getByTestId(`balance-${no}`);
export const saveButton = () => screen.getByRole('button', { name: /^save$/i });

/** Type a qty the way a person does: focus, change, leave. */
export function typeQty(no: number, n: number, value: string) {
  const input = qty(no, n);
  act(() => input.focus());
  fireEvent.change(input, { target: { value } });
}

/** Type a date (DD/MM/YYYY) and commit it by leaving the cell. */
export function typeDate(no: number, n: number, value: string) {
  const input = dateIn(no, n);
  act(() => input.focus());
  fireEvent.change(input, { target: { value } });
  act(() => input.blur());
}

/** Move real focus out of the sheet (the dialog's search box). */
export function leaveSheet() {
  const search = screen.getByPlaceholderText(/item code/i);
  act(() => search.focus());
}

/** Click a REMAIN qty cell and wait for the split row it turns into. */
export async function splitLine(no: number) {
  fireEvent.click(remainQty(no));
  return screen.findByLabelText(`Quantity, line ${no} split 1`);
}

export function blockOf(el: Element) {
  return el.closest('tbody') as HTMLElement;
}

/**
 * Variant B (AC-G2): where split `n` of line `origin` is drawn. `inBlock` = it sits in line
 * `target`'s block; `lineCell` = its own LINE cell reads `origin`.
 */
export function drawnUnder(target: number, origin: number, n: number) {
  const row = qty(origin, n).closest('tr') as HTMLTableRowElement;
  return {
    inBlock: block(target).contains(row),
    lineCell: Array.from(row.cells).some(
      (td) => (td.textContent ?? '').trim() === String(origin),
    ),
  };
}

/** The retired destination label (owner "no labels", AC-G11): `+236 from line 480`. */
export const FROM_LINE_LABEL = /\+\d+ from line/;

export const within_ = within;

/** Every message handed to a toast function, with its options. */
export function toastCalls(...fns: Array<{ mock: { calls: unknown[][] } }>) {
  return fns.flatMap((f) => f.mock.calls.map((c) => ({ msg: String(c[0]), opts: c[1] as
    | { action?: { label: string; onClick: () => void } }
    | undefined })));
}


/**
 * OI-SPLIT-VIEW round 4 (UAC E): SO417636 as `LineSplitService.read` serves it once the owner's
 * plan is applied: 480 = 14 own + 236 and 167 on a New line; 752 = 37 own + 467 on a New line
 * and the AutoCount extra 145; 608 and 768 carry no split. `edited` marks 480 as saved but not
 * confirmed (`split_state` 'acting'); applied lines read 'applied'.
 */
export function ownerSavedCase(opts: { edited?: boolean; confirmedAt?: string | null } = {}) {
  const state = opts.edited ? 'acting' : 'applied';
  return {
    pso_id: PSO,
    so_number: 'SO417636',
    so_date: '2026-09-03',
    customer: 'GLOBAL INGRESS SDN BHD (PROJECT)',
    project: '405U + 397U PANGSAPURI',
    confirmed_at: opts.edited ? null : (opts.confirmedAt ?? '2026-10-19'),
    lines: [
      wireLine(480, 'CSK14B', 417, '2026-10-20', {
        now_qty: 14,
        now_date: '2026-09-20',
        split_state: state,
        splits: [
          wireSplit('s14', 14, '2026-09-20', 'L480'),
          wireSplit('s236', 236, '2026-11-20', null),
          wireSplit('s167', 167, '2026-11-20', null),
        ],
      }),
      wireLine(608, 'CSK14B', 632, '2026-11-20'),
      wireLine(752, 'CSK14B', 504, '2026-12-20', {
        now_qty: 649,
        now_date: '2027-01-02',
        split_state: 'applied',
        extra_qty: 145,
        extra_remark: 'ORDER 145',
        splits: [
          wireSplit('t37', 37, '2026-11-20', 'L752'),
          wireSplit('t467', 467, '2027-01-02', null),
        ],
      }),
      wireLine(768, 'CSK11A', 335, '2027-01-02'),
    ],
  };
}

/** 480 moves 236 onto line 608 (which carries no split of its own): variant B. */
export function receivingCase() {
  const p = ownerSavedCase();
  p.lines[0].splits = [
    wireSplit('s14', 14, '2026-09-20', 'L480'),
    wireSplit('s236', 236, '2026-11-20', 'L608'),
    wireSplit('s167', 167, '2026-11-20', null),
  ];
  return p;
}

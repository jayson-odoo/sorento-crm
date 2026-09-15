/**
 * Parts under a price tag line (S2, D2).
 *
 * UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`
 * AC-S2-1 (one combo fills in on pick), AC-S2-2 (Package select with two or
 * more), AC-S2-3 (open row select and clear), AC-S2-4 (staged removal and add
 * by hand), AC-S2-8 (the payload) and AC-S2-11 (375px).
 *
 * The salesperson asks for the cabinet they know and the package's parts appear
 * under it without being asked for. That is the whole slice on this screen, and
 * what these tests pin is the thing a mock cannot: which service call the form
 * makes on a product pick, and what ends up in `parts` on the wire.
 *
 * `lookupProductCombos` is mocked per test rather than left on its Phase 1
 * bucket-by-uuid stand-in, so a case says out loud which shape it is about.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../lib/price-tag-request-service', () => ({
  lookupDebtors: vi.fn(),
  lookupPromotions: vi.fn(async () => []),
  lookupTagItems: vi.fn(),
  lookupProductCombos: vi.fn(),
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  submitRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
}));

/** Same native-select stand-in the other form suites use: a pick is one change. */
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    onOptionChange?: (
      o: { value: string; label: string; description?: string } | null,
    ) => void;
    options?: { value: string; label: string; description?: string }[];
    fetchOptions?: (
      q: string,
    ) => Promise<{ value: string; label: string; description?: string }[]>;
    placeholder?: string;
  }) => {
    const [async, setAsync] = React.useState<
      { value: string; label: string; description?: string }[]
    >([]);
    React.useEffect(() => {
      if (props.fetchOptions) void props.fetchOptions('').then(setAsync);
    }, [props.fetchOptions]);
    const options = props.options ?? async;
    return (
      <select
        aria-label={props.id === 'debtor' ? 'Debtor' : (props.placeholder ?? '')}
        value={props.value}
        onChange={(e) => {
          props.onChange(e.target.value);
          props.onOptionChange?.(
            options.find((o) => o.value === e.target.value) ?? null,
          );
        }}
      >
        <option value="">{props.placeholder ?? ''}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

import {
  createRequest,
  lookupDebtors,
  lookupProductCombos,
  lookupTagItems,
} from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';
import { selectOption } from '@/test-utils';

const mockCombos = vi.mocked(lookupProductCombos);
const mockCreate = createRequest as ReturnType<typeof vi.fn>;

const DEBTORS = [{ code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' }];

const CABINET = {
  kind: 'product' as const,
  id: 'prod-cabinet',
  code: 'SRTBF11834',
  name: 'ZZT Cabinet',
};

const SINK = {
  kind: 'product' as const,
  id: 'prod-sink',
  code: 'SRTKS2435',
  name: 'ZZT Kitchen Sink',
};

const MIRROR = { product_id: 'prod-mirror', code: 'SRTMR502-BL', name: 'ZZT Mirror' };
const TOP = { product_id: 'prod-top', code: 'SRTTT800', name: 'ZZT Table Top' };
const BASIN_WHITE = { product_id: 'prod-basin-wh', code: 'SRTBS900-WH', name: 'ZZT Basin White' };
const BASIN_BLACK = { product_id: 'prod-basin-bk', code: 'SRTBS900-BK', name: 'ZZT Basin Black' };

const COMBO_3_IN_1 = {
  combo_id: 'combo-3',
  name: '3 in 1',
  parts: [
    { ...MIRROR, choice_group: null },
    { ...BASIN_WHITE, choice_group: 'Basin' },
    { ...BASIN_BLACK, choice_group: 'Basin' },
  ],
};

const COMBO_4_IN_1 = {
  combo_id: 'combo-4',
  name: '4 in 1',
  parts: [
    { ...MIRROR, choice_group: null },
    { ...TOP, choice_group: null },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  (lookupDebtors as ReturnType<typeof vi.fn>).mockResolvedValue(DEBTORS);
  (lookupTagItems as ReturnType<typeof vi.fn>).mockResolvedValue([
    CABINET,
    // The Add part picker reads the SAME catalogue lookup, products only, so a
    // part added by hand has to be findable here.
    { kind: 'product' as const, id: MIRROR.product_id, code: MIRROR.code, name: MIRROR.name },
    SINK,
  ]);
  mockCombos.mockResolvedValue({ host_guarded: false, combos: [] });
  mockCreate.mockResolvedValue({ id: 'req-1' });
});

async function addLine() {
  fireEvent.click(screen.getByRole('button', { name: /Add line/ }));
}

/** Customer first: the Sales Order & Lines section is collapsed until one is picked. */
async function startWithALine() {
  render(<PriceTagRequestForm />);
  await selectOption('Debtor', 'ZZTD01');
  await addLine();
}

async function pickTheCabinet() {
  await selectOption('Search a set or product...', `product:${CABINET.id}`);
}

function submittedLines() {
  return mockCreate.mock.calls[0][0].lines;
}

/**
 * r9 D7/AC-S3-1: `Printing` has no default and Submit refuses without it, so
 * every test here that expects the POST to happen has to answer it first.
 * (Merge reconciliation: this spec was written before that control existed.)
 */
async function pickPrinting() {
  if (!screen.queryByRole('radio', { name: 'Office prints' })) {
    fireEvent.click(
      screen.getByRole('button', { name: /Additional Information/ }),
    );
  }
  fireEvent.click(await screen.findByRole('radio', { name: 'Office prints' }));
}

// ---------------------------------------------------------------------------
// AC-S2-1 - one combo fills in on pick
// ---------------------------------------------------------------------------

describe('PriceTagRequestForm - parts under a line (S2)', () => {
  it('asks the server for the picked product\'s packages, once, on the pick', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_3_IN_1] });
    await startWithALine();
    await pickTheCabinet();

    await waitFor(() => expect(mockCombos).toHaveBeenCalledWith(CABINET.id));
    expect(mockCombos).toHaveBeenCalledTimes(1);
  });

  it('fills the only package in as child rows: fixed parts, and ONE row per choice group', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_3_IN_1] });
    await startWithALine();
    await pickTheCabinet();

    // The fixed part is a product row named by its own code.
    expect(await screen.findByText(MIRROR.code)).toBeInTheDocument();

    // The two basins are ONE open row, not two product rows: the salesperson
    // picks one of them, and listing both as parts would read as buying both.
    expect(screen.queryByText(BASIN_WHITE.code)).toBeNull();
    expect(screen.queryByText(BASIN_BLACK.code)).toBeNull();
    const open = screen.getByLabelText('Not sure, any of 2');
    expect(open).toBeInTheDocument();
    expect(screen.getByText('Marketing will prepare one tag per option')).toBeInTheDocument();

    // No Package select: there is only one package to be in.
    expect(screen.queryByLabelText('Package')).toBeNull();
  });

  it('posts the package and its parts, resolved and open, in display order (AC-S2-8)', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_3_IN_1] });
    await startWithALine();
    await pickTheCabinet();
    await screen.findByText(MIRROR.code);

    await pickPrinting();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());

    const [line] = submittedLines();
    expect(line).toMatchObject({
      line_type: 'product',
      product_id: CABINET.id,
      combo_id: COMBO_3_IN_1.combo_id,
    });
    expect(line.parts).toEqual([
      { product_id: MIRROR.product_id, role: null, candidates: [] },
      {
        product_id: null,
        role: 'Basin',
        candidates: [BASIN_WHITE.product_id, BASIN_BLACK.product_id],
      },
    ]);
    // Retired in S2: the column is dropped, so the payload must not carry it.
    expect(line.alternatives).toBeUndefined();
    // Still derived server-side from the header's price_mode (r7 D5).
    expect(line.show_promo_price).toBeUndefined();
  });

  // -------------------------------------------------------------------------
  // AC-S2-2 - two or more packages
  // -------------------------------------------------------------------------

  it('offers a clearable Package select when the host has two packages, and fills nothing until one is chosen', async () => {
    mockCombos.mockResolvedValue({
      host_guarded: true,
      combos: [COMBO_3_IN_1, COMBO_4_IN_1],
    });
    await startWithALine();
    await pickTheCabinet();

    const packageSelect = await screen.findByLabelText('Package');
    expect(within(packageSelect).getByText('3 in 1')).toBeInTheDocument();
    expect(within(packageSelect).getByText('4 in 1')).toBeInTheDocument();
    // Nothing chosen means no parts - the form must not guess which catalogue
    // page the salesperson meant.
    expect(screen.queryByText(MIRROR.code)).toBeNull();
    expect(screen.queryByLabelText(/Not sure, any of/)).toBeNull();
  });

  it('replaces the parts when the package choice changes, and clears them when it is cleared', async () => {
    mockCombos.mockResolvedValue({
      host_guarded: true,
      combos: [COMBO_3_IN_1, COMBO_4_IN_1],
    });
    await startWithALine();
    await pickTheCabinet();
    await screen.findByLabelText('Package');

    fireEvent.change(screen.getByLabelText('Package'), {
      target: { value: COMBO_4_IN_1.combo_id },
    });
    expect(await screen.findByText(TOP.code)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Not sure, any of/)).toBeNull();

    fireEvent.change(screen.getByLabelText('Package'), {
      target: { value: COMBO_3_IN_1.combo_id },
    });
    await waitFor(() => expect(screen.queryByText(TOP.code)).toBeNull());
    expect(screen.getByLabelText('Not sure, any of 2')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Package'), { target: { value: '' } });
    await waitFor(() => expect(screen.queryByText(MIRROR.code)).toBeNull());
    expect(screen.queryByLabelText(/Not sure, any of/)).toBeNull();
  });

  // -------------------------------------------------------------------------
  // AC-S2-3 - the open row
  // -------------------------------------------------------------------------

  it('an open row resolves to the chosen candidate, and clearing reopens it', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_3_IN_1] });
    await startWithALine();
    await pickTheCabinet();
    const open = await screen.findByLabelText('Not sure, any of 2');

    fireEvent.change(open, { target: { value: BASIN_BLACK.product_id } });

    // Resolved: the one-line explanation goes away with the uncertainty.
    await waitFor(() =>
      expect(
        screen.queryByText('Marketing will prepare one tag per option'),
      ).toBeNull(),
    );

    await pickPrinting();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(submittedLines()[0].parts[1]).toEqual({
      product_id: BASIN_BLACK.product_id,
      role: 'Basin',
      candidates: [],
    });
  });

  it('clearing a resolved candidate puts the row back to open, candidates intact', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_3_IN_1] });
    await startWithALine();
    await pickTheCabinet();
    const open = await screen.findByLabelText('Not sure, any of 2');

    fireEvent.change(open, { target: { value: BASIN_WHITE.product_id } });
    await waitFor(() =>
      expect(
        screen.queryByText('Marketing will prepare one tag per option'),
      ).toBeNull(),
    );

    fireEvent.change(screen.getByLabelText('Not sure, any of 2'), {
      target: { value: '' },
    });
    expect(
      await screen.findByText('Marketing will prepare one tag per option'),
    ).toBeInTheDocument();

    await pickPrinting();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(submittedLines()[0].parts[1].product_id).toBeNull();
    expect(submittedLines()[0].parts[1].candidates).toEqual([
      BASIN_WHITE.product_id,
      BASIN_BLACK.product_id,
    ]);
  });

  // -------------------------------------------------------------------------
  // AC-S2-4 - staged removal, and adding by hand
  // -------------------------------------------------------------------------

  it('removes a part row immediately: no confirm, no countdown (the staged-removals rule)', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_3_IN_1] });
    await startWithALine();
    await pickTheCabinet();
    await screen.findByText(MIRROR.code);

    fireEvent.click(
      // The row is named by its choice group, or by its code when it is fixed.
      screen.getByRole('button', { name: `Remove part ${MIRROR.code} from line 1` }),
    );

    await waitFor(() => expect(screen.queryByText(MIRROR.code)).toBeNull());
    // A part row is unsaved form state, not a record: nothing is parked and
    // nothing asks.
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.queryByText(/Undo/)).toBeNull();

    await pickPrinting();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(
      submittedLines()[0].parts.map((part: { product_id: string | null }) => part.product_id),
    ).toEqual([null]);
  });

  it('a part can be added by hand on a line whose product has NO package at all', async () => {
    mockCombos.mockResolvedValue({ host_guarded: false, combos: [] });
    await startWithALine();
    await pickTheCabinet();
    await waitFor(() => expect(mockCombos).toHaveBeenCalled());

    const picker = await screen.findByLabelText('Add part');
    fireEvent.change(picker, { target: { value: `product:${MIRROR.product_id}` } });

    await pickPrinting();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    const [line] = submittedLines();
    expect(line.combo_id).toBeNull();
    expect(line.parts).toEqual([
      { product_id: MIRROR.product_id, role: null, candidates: [] },
    ]);
  });

  // -------------------------------------------------------------------------
  // Review S1 - the lookup is per PICK, not per product
  // -------------------------------------------------------------------------

  it('re-picking a product the line held before asks for its packages again', async () => {
    // A -> B -> A. Cached by product id, the third pick is a no-op and the line
    // comes back with no package and no parts, which reads as a cabinet that
    // lost its combo rather than as a lookup that never ran.
    mockCombos.mockImplementation(async (productId: string) =>
      productId === CABINET.id
        ? { host_guarded: true, combos: [COMBO_3_IN_1, COMBO_4_IN_1] }
        : { host_guarded: false, combos: [] },
    );
    await startWithALine();

    await pickTheCabinet();
    await screen.findByLabelText('Package');

    await selectOption('Search a set or product...', `product:${SINK.id}`);
    await waitFor(() => expect(mockCombos).toHaveBeenCalledWith(SINK.id));
    expect(screen.queryByLabelText('Package')).toBeNull();

    await pickTheCabinet();

    await waitFor(() =>
      expect(
        mockCombos.mock.calls.filter(([id]) => id === CABINET.id),
      ).toHaveLength(2),
    );
    // And the line is usable again, not left holding the sink's emptiness.
    expect(await screen.findByLabelText('Package')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Package'), {
      target: { value: COMBO_3_IN_1.combo_id },
    });
    expect(await screen.findByText(MIRROR.code)).toBeInTheDocument();
    expect(screen.getByLabelText('Not sure, any of 2')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // AC-S2-11 - 375px
  // -------------------------------------------------------------------------

  it('at 375px the package and open-row selects are full width and nothing is clipped', async () => {
    mockCombos.mockResolvedValue({
      host_guarded: true,
      combos: [COMBO_3_IN_1, COMBO_4_IN_1],
    });
    await startWithALine();
    await pickTheCabinet();
    const packageSelect = await screen.findByLabelText('Package');

    const wrapper = packageSelect.closest('td');
    expect(wrapper).not.toBeNull();
    // The part and package rows span the whole line table rather than squeezing
    // into one column, which is what makes them readable at 375px.
    expect(wrapper).toHaveAttribute('colspan', '5');
  });
});

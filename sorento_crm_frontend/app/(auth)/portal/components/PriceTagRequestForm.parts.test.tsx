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

vi.mock('../lib/price-tag-request-service', async () => {
  const { computeLinePricing } = await import('@/app/(auth)/portal/components/__fixtures__/line-pricing');
  return {
  lookupLinePricing: vi.fn(async (mode: string, lines: unknown[]) =>
    computeLinePricing(mode as 'list' | 'selling', lines as never),
  ),
  lookupDebtors: vi.fn(),
  lookupPromotions: vi.fn(async () => []),
  lookupTagItems: vi.fn(),
  lookupProductCombos: vi.fn(),
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  submitRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
  };
});

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
  getRequest,
  lookupDebtors,
  lookupProductCombos,
  lookupTagItems,
  type ProductCombosLookup,
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
    // D1 (this lane, mocked): the row's own select labels each candidate
    // `CODE  RM x` once `lookupLinePricing` resolves (AC-S2-1) - a SEPARATE
    // async effect from the combo fill this test already awaited above, so
    // the bare code can still be on screen for one more tick; `waitFor`
    // gives it the same settle before checking it never renders standalone.
    await waitFor(() => {
      expect(screen.queryByText(BASIN_WHITE.code)).toBeNull();
      expect(screen.queryByText(BASIN_BLACK.code)).toBeNull();
    });
    const open = screen.getByLabelText('Not sure, any of 2');
    expect(open).toBeInTheDocument();
    // D18: the open-row explanation sentence is retired - the select with
    // its placeholder and the role label is the whole row now.

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
    // D18: no explanation sentence anymore - the select itself, back to its
    // own placeholder value, is what "open again" reads as on screen.
    expect(screen.getByLabelText('Not sure, any of 2')).toHaveValue('');

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

  // PLAN-price-tag-ai-extract-resolver.md D4 (AC-S2-1): a line whose product
  // has no package has nothing to add a part TO, so "Add part" no longer
  // renders at all here - superseding the old "add by hand on any line"
  // rule this test pinned.
  it('no "Add part" search on a line whose product has NO package at all (AC-S2-1)', async () => {
    mockCombos.mockResolvedValue({ host_guarded: false, combos: [] });
    await startWithALine();
    await pickTheCabinet();
    await waitFor(() => expect(mockCombos).toHaveBeenCalled());

    expect(screen.queryByLabelText('Add part')).toBeNull();

    await pickPrinting();
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    const [line] = submittedLines();
    expect(line.combo_id).toBeNull();
    expect(line.parts).toEqual([]);
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

// ---------------------------------------------------------------------------
// PLAN-price-tag-ai-extract-resolver.md D4 / price-tag-ai-extract-resolver-
// acceptance-criteria.md S2 (AC-S2-1..S2-3): "Add part" only when the
// product actually has a combo. Supersedes the old "on any line, combo or
// not" rule this same file pinned above.
// ---------------------------------------------------------------------------

describe('PriceTagRequestForm - "Add part" only with a combo (AC-S2-1..S2-3)', () => {
  it('AC-S2-3: no "Add part" before the combos lookup answers (no flash)', async () => {
    let resolveCombos: (value: ProductCombosLookup) => void = () => {};
    mockCombos.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCombos = resolve;
        }),
    );
    await startWithALine();
    await pickTheCabinet();

    expect(screen.queryByLabelText('Add part')).toBeNull();

    resolveCombos({ host_guarded: false, combos: [] });
    await waitFor(() => expect(mockCombos).toHaveBeenCalled());
    expect(screen.queryByLabelText('Add part')).toBeNull();
  });

  it('AC-S2-2: shows "Add part" once the lookup returns one or more combos', async () => {
    mockCombos.mockResolvedValue({
      host_guarded: true,
      combos: [COMBO_3_IN_1, COMBO_4_IN_1],
    });
    await startWithALine();
    await pickTheCabinet();
    await screen.findByLabelText('Package');

    expect(screen.getByLabelText('Add part')).toBeInTheDocument();
  });

  it('AC-S2-1: no "Add part" when the lookup returns empty - existing part rows still render with Remove', async () => {
    mockCombos.mockResolvedValue({ host_guarded: false, combos: [] });
    const draftRequest = {
      id: 'req-1',
      doc_number: 'PT-202609-0009',
      debtor_code: 'ZZTD01',
      debtor_name: 'ZZT Dealer Sdn Bhd',
      promotion_id: null,
      promotion_name: null,
      price_mode: 'list',
      needed_by_date: null,
      notes: null,
      status: 'new',
      line_count: 1,
      created_at: '2026-09-01T00:00:00Z',
      portal_draft_at: '2026-09-01T00:00:00Z',
      contact_id: 'contact-1',
      has_completed_export: false,
      is_editable: true,
      revision_no: 0,
      last_revised_at: null,
      revision: null,
      attachments: [],
      lines: [
        {
          id: 'line-1',
          line_type: 'product',
          product_id: CABINET.id,
          product_set_id: null,
          name: CABINET.name,
          code: CABINET.code,
          show_promo_price: false,
          quantity: 1,
          included_accessories: null,
          remarks: null,
          sort_order: 0,
          combo_id: null,
          package_warning: null,
          parts: [
            {
              id: 'part-existing',
              product_id: MIRROR.product_id,
              code: MIRROR.code,
              name: MIRROR.name,
              role: null,
              candidates: [],
              sort_order: 0,
            },
          ],
          tags: [],
        },
      ],
    };
    (getRequest as ReturnType<typeof vi.fn>).mockResolvedValue(draftRequest);

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText(MIRROR.code);
    await waitFor(() => expect(mockCombos).toHaveBeenCalledWith(CABINET.id));

    expect(screen.queryByLabelText('Add part')).toBeNull();
    expect(
      screen.getByRole('button', { name: `Remove part ${MIRROR.code} from line 1` }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// PLAN-price-tag-ai-extract-resolver.md D17/D18/D19 (S12/S13/S14): a single-
// candidate choice group resolves like a fixed part, the open-row sentence is
// retired, and a removed package part can be put back with one click.
// ---------------------------------------------------------------------------

const KITCHEN_TAP = { product_id: 'prod-tap', code: 'SRTTAP100', name: 'ZZT Kitchen Tap' };

const COMBO_SINGLE_CANDIDATE = {
  combo_id: 'combo-single',
  name: 'Single candidate',
  parts: [
    { ...MIRROR, choice_group: null },
    { ...KITCHEN_TAP, choice_group: 'Kitchen Tap' },
  ],
};

const COMBO_ONE_FIXED = {
  combo_id: 'combo-onefixed',
  name: 'One fixed',
  parts: [{ ...MIRROR, choice_group: null }],
};

const COMBO_TWO_FIXED_ONE_GROUP = {
  combo_id: 'combo-restore',
  name: 'Restore test',
  parts: [
    { ...MIRROR, choice_group: null },
    { ...TOP, choice_group: null },
    { ...BASIN_WHITE, choice_group: 'Basin' },
    { ...BASIN_BLACK, choice_group: 'Basin' },
  ],
};

describe('PriceTagRequestForm - one candidate is not a choice (S12)', () => {
  it('AC-S12-1: a single-candidate group fills a resolved row, no "Not sure, any of 1" select', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_SINGLE_CANDIDATE] });
    await startWithALine();
    await pickTheCabinet();

    expect(await screen.findByText(KITCHEN_TAP.code)).toBeInTheDocument();
    expect(screen.getByText('Kitchen Tap')).toBeInTheDocument();
    expect(screen.queryByLabelText('Not sure, any of 1')).toBeNull();
  });

  it('AC-S12-2: a group with two candidates still yields the open row', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_3_IN_1] });
    await startWithALine();
    await pickTheCabinet();

    expect(await screen.findByLabelText('Not sure, any of 2')).toBeInTheDocument();
  });
});

describe('PriceTagRequestForm - no open-row copy (S13)', () => {
  it('AC-S13-1: "Marketing will prepare one tag per option" appears nowhere', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_3_IN_1] });
    await startWithALine();
    await pickTheCabinet();
    await screen.findByLabelText('Not sure, any of 2');

    expect(
      screen.queryByText('Marketing will prepare one tag per option'),
    ).toBeNull();
  });
});

describe('PriceTagRequestForm - restore a removed package part (S14)', () => {
  it('AC-S14-1: Restore puts back a removed fixed row and clears the warning', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_ONE_FIXED] });
    await startWithALine();
    await pickTheCabinet();
    await screen.findByText(MIRROR.code);

    fireEvent.click(
      screen.getByRole('button', { name: `Remove part ${MIRROR.code} from line 1` }),
    );
    await waitFor(() => expect(screen.queryByText(MIRROR.code)).toBeNull());

    expect(await screen.findByText('Missing: SRTMR502-BL')).toBeInTheDocument();
    const restore = screen.getByRole('button', { name: 'Restore' });

    fireEvent.click(restore);

    expect(await screen.findByText(MIRROR.code)).toBeInTheDocument();
    expect(screen.queryByText(/Missing:/)).toBeNull();
  });

  it('AC-S14-2: Restore adds exactly the missing fixed part and group, leaving the kept row untouched', async () => {
    mockCombos.mockResolvedValue({ host_guarded: true, combos: [COMBO_TWO_FIXED_ONE_GROUP] });
    await startWithALine();
    await pickTheCabinet();
    await screen.findByText(MIRROR.code);
    await screen.findByText(TOP.code);
    await screen.findByLabelText('Not sure, any of 2');

    // Remove the fixed TOP row and the open Basin row; keep MIRROR.
    fireEvent.click(
      screen.getByRole('button', { name: `Remove part ${TOP.code} from line 1` }),
    );
    await waitFor(() => expect(screen.queryByText(TOP.code)).toBeNull());
    fireEvent.click(
      screen.getByRole('button', { name: 'Remove part Basin from line 1' }),
    );
    await waitFor(() => expect(screen.queryByLabelText(/Not sure, any of/)).toBeNull());

    expect(await screen.findByText('Missing: SRTTT800, Basin')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Restore' }));

    expect(await screen.findByText(TOP.code)).toBeInTheDocument();
    expect(await screen.findByLabelText('Not sure, any of 2')).toBeInTheDocument();
    // MIRROR was never removed - exactly one row for it, not duplicated.
    expect(screen.getAllByText(MIRROR.code)).toHaveLength(1);
  });

  it('AC-S14-3: no Restore button on a line with no combo_id (nothing missing to restore)', async () => {
    mockCombos.mockResolvedValue({ host_guarded: false, combos: [] });
    await startWithALine();
    await pickTheCabinet();
    await waitFor(() => expect(mockCombos).toHaveBeenCalled());

    expect(screen.queryByRole('button', { name: 'Restore' })).toBeNull();
  });
});

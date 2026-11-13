/** SO-CANCEL-LINE (AC-F1, AC-F2, AC-F3): the Decide menu's "Transfer to Cancel SO" item. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '@/lib/toast';
import { BoardDecideControl } from './BoardDecideControl';
import { suggestedDecisionFor } from '../../_shared/lib/boardAmend';
import type { BoardContribution } from '../../_shared/types/fulfilmentPlanning.types';

vi.mock('@/lib/toast', () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <select aria-label="donor-or-location" />,
}));

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

function row(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: 'so-1:line-10',
    sales_order_id: 'so-1',
    so_number: 'SO900001',
    line_no: 10,
    item_code: 'CB110',
    qty: '36',
    unplannable: false,
    cancelled: false,
    rank_score: 1,
    rank_factors: [],
    sources: [{ kind: 'buy', qty: '36', reason: 'Nothing free.' }],
    contested: false,
    covered: false,
    locations: [],
    borrow_candidates: [],
    ...overrides,
  };
}

function renderControl(contributions: BoardContribution[]) {
  const onSave = vi.fn(async (entries: { key: string }[]) => ({
    savedKeys: entries.map((entry) => entry.key),
    failed: [],
  }));
  render(
    <BoardDecideControl
      contributions={contributions}
      selectedKeys={contributions.map((c) => c.key)}
      draft={{}}
      onSave={onSave as never}
      onSaved={vi.fn()}
      onClear={vi.fn()}
      borrowFromOrderEnabled
    />,
  );
  return { onSave };
}

function openMenu() {
  fireEvent.keyDown(screen.getByTestId('board-decide-button'), { key: 'Enter' });
}

beforeEach(() => vi.clearAllMocks());

describe('Transfer to Cancel SO in the Decide menu', () => {
  it('AC-F1: is the last of seven items, the other six unchanged', () => {
    renderControl([row()]);
    openMenu();
    expect(screen.getAllByRole('menuitem').map((item) => item.textContent)).toEqual([
      'As suggested',
      'Use own location',
      'Borrow from another order',
      'Borrow',
      'Use BRW',
      'Buy',
      'Cancel',
    ]);
  });

  it('AC-F2: opens "Decide 1 line: Transfer to Cancel SO" with a Reason and no picker; Save needs a reason', async () => {
    renderControl([row()]);
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Cancel' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent(/Decide 1 lines?: Cancel/);
    expect(within(dialog).queryByLabelText('donor-or-location')).not.toBeInTheDocument();
    const save = within(dialog).getByRole('button', { name: /^Save/ });
    expect(save).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: '   ' } });
    expect(save).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Customer cancelled' } });
    expect(save).toBeEnabled();
  });

  it('AC-F3: saves a cancelled-verdict decision per uncovered row and names the skipped ones', async () => {
    const ok = row();
    const covered = row({
      key: 'so-1:line-20',
      line_no: 20,
      item_code: 'CB110-R',
      covered: true,
      decision: {
        revision_no: 1,
        timely_spo_qty: '0',
        reserve: [],
        borrow: [],
        buy_qty: '36',
      },
    });
    const gone = row({ key: 'so-1:line-30', line_no: 30, item_code: 'CB110LP', cancelled: true });
    const { onSave } = renderControl([ok, covered, gone]);
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Cancel' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Customer cancelled' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^Save/ }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const [entries] = onSave.mock.calls[0] as unknown as [{ key: string; decision: unknown }[]];
    expect(entries).toEqual([
      {
        key: ok.key,
        decision: expect.objectContaining({
          verdict: 'cancelled',
          reason: 'Customer cancelled',
          reserve: [],
          borrow: [],
          timely_spo_qty: '0',
          buy_qty: '0',
        }),
      },
    ]);
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringMatching(/^1 saved as Cancel · 2 skipped: /),
      ),
    );
  });
});

describe('Transfer to Cancel SO names the rows it skips (AC-F18)', () => {
  const decision = {
    revision_no: 1,
    timely_spo_qty: '0',
    reserve: [],
    borrow: [],
    buy_qty: '36',
  };
  const confirmed = (n: number) =>
    row({ key: `so-1:line-${n}`, line_no: n, covered: true, decision });

  async function openCancel(contributions: BoardContribution[]) {
    renderControl(contributions);
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Cancel' }));
    return screen.findByRole('dialog');
  }

  it('all three confirmed: says so and Save 0 lines is disabled', async () => {
    const dialog = await openCancel([confirmed(10), confirmed(20), confirmed(30)]);
    expect(dialog).toHaveTextContent('3 lines will be skipped: confirmed, reject it first');
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Customer cancelled' } });
    const save = within(dialog).getByRole('button', { name: 'Save 0 lines' });
    expect(save).toBeDisabled();
  });

  it('mixed: 1 skipped sentence, Save 2 lines enabled once a reason is typed', async () => {
    const dialog = await openCancel([
      row({ key: 'so-1:line-10', line_no: 10 }),
      row({ key: 'so-1:line-20', line_no: 20 }),
      confirmed(30),
    ]);
    expect(dialog).toHaveTextContent('1 line will be skipped: confirmed, reject it first');
    const save = within(dialog).getByRole('button', { name: 'Save 2 lines' });
    expect(save).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Customer cancelled' } });
    expect(save).toBeEnabled();
  });

  it('nothing skipped: no skip sentence', async () => {
    const dialog = await openCancel([row()]);
    expect(dialog.textContent).not.toMatch(/will be skipped/);
  });
});

describe('Borrow dialog before a pick (AC-F21)', () => {
  it.each(['Borrow from another order', 'Borrow'])(
    '%s: no "will be skipped" sentence until a donor or location is picked',
    async (item) => {
      renderControl([row(), row({ key: 'so-1:line-20', line_no: 20 })]);
      openMenu();
      fireEvent.click(screen.getByRole('menuitem', { name: item }));
      const dialog = await screen.findByRole('dialog');
      expect(dialog.textContent).not.toMatch(/will be skipped/);
    },
  );
});

describe('Decide > Cancel on book-cancelled lines (OI-WHOLE-SO-CANCEL)', () => {
  const bookCancelled = (n: number) =>
    row({
      key: `so-1:line-${n}`,
      line_no: n,
      qty: '0',
      sources: [],
      cancelled: true,
      cancelled_at: null,
      pending_change_batch_id: 'b1',
    } as Partial<BoardContribution>);

  async function pickCancel() {
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Cancel' }));
    const dialog = screen.queryByRole('dialog');
    if (dialog) {
      const reason = within(dialog).queryByLabelText(/^Reason/);
      if (reason) fireEvent.change(reason, { target: { value: 'Customer cancelled' } });
      fireEvent.click(within(dialog).getByRole('button', { name: /^Save/ }));
    }
  }

  it('saves each ticked book-cancelled row with exactly suggestedDecisionFor(row)', async () => {
    const rows = [bookCancelled(10), bookCancelled(20), bookCancelled(30)];
    const { onSave } = renderControl(rows);
    await pickCancel();

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const entries = onSave.mock.calls.flatMap(
      (call) => call[0] as unknown as { key: string; decision: unknown }[],
    );
    expect(entries).toEqual(
      rows.map((r) => ({ key: r.key, decision: suggestedDecisionFor(r) })),
    );
    expect(entries.map((e) => e.decision)).toEqual([
      { verdict: 'approved' },
      { verdict: 'approved' },
      { verdict: 'approved' },
    ]);
  });

  it('guard: a line that is not book-cancelled picked with Cancel still saves verdict cancelled', async () => {
    const { onSave } = renderControl([row()]);
    await pickCancel();

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const [entries] = onSave.mock.calls[0] as unknown as [{ decision: { verdict: string } }[]];
    expect(entries[0].decision.verdict).toBe('cancelled');
  });
});

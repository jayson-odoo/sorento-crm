/** Point ratio (lane SALES-TARGET-DEALER, UAC D4-4; lane POINT-RATIO-EDIT): the dated history,
 * adding a ratio, and each row's Edit (in place) and Delete (deferred, D7). */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';

vi.mock('@/lib/helpers', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/helpers')>()),
  todayMalaysiaYyyyMmDd: () => '2026-10-01',
}));
vi.mock('@/components/ui/date-picker', () => ({
  // A plain yyyy-mm-dd box standing in for the picker, so a test can change the date.
  DatePicker: ({
    ariaLabel,
    value,
    onChange,
  }: {
    ariaLabel?: string;
    value?: Date;
    onChange?: (d?: Date) => void;
  }) => (
    <input
      aria-label={ariaLabel}
      value={
        value
          ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
          : ''
      }
      onChange={(e) =>
        onChange?.(
          e.target.value ? new Date(`${e.target.value}T12:00:00`) : undefined,
        )
      }
    />
  ),
}));

const save = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const ratios = vi.hoisted(() => ({
  rows: [
    { id: 'r2', effective_from: '2026-10-01', rm_per_point: 1.3 },
    { id: 'r1', effective_from: '2026-01-01', rm_per_point: 1.2 },
  ],
}));
const update = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const deletion = vi.hoisted(() => ({
  run: vi.fn(),
  targetId: null as string | null,
  isPending: false,
  countdown: null as React.ReactNode,
}));
const deferredInput = vi.hoisted(() => ({
  current: null as Record<string, unknown> | null,
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: Record<string, unknown>) => {
    deferredInput.current = input;
    return deletion;
  },
}));
vi.mock('../hooks/useSalesTargets', () => ({
  POINT_RATIOS_KEY: ['sales-target-point-ratios'],
  SALES_TARGETS_KEY: ['sales-targets'],
  SALES_TARGET_KEY: ['sales-target'],
  usePointRatios: () => ({ data: ratios, isLoading: false }),
  useSavePointRatio: () => save,
  useUpdatePointRatio: () => update,
}));

import PointRatioDialog from './PointRatioDialog';

beforeEach(() => {
  save.mutateAsync.mockReset();
  save.mutateAsync.mockResolvedValue({ id: 'r3' });
  update.mutateAsync.mockReset();
  update.mutateAsync.mockResolvedValue({ id: 'r1' });
  deletion.run.mockReset();
  deletion.targetId = null;
  deletion.countdown = null;
});

describe('PointRatioDialog', () => {
  it('lists the ratios newest first', () => {
    render(<PointRatioDialog open onOpenChange={() => {}} />);
    const rows = within(screen.getByRole('table', { name: 'Point ratios' }))
      .getAllByRole('row')
      .slice(1);
    expect(rows.map((r) => r.textContent)).toEqual([
      '01/10/20261.3',
      '01/01/20261.2',
    ]);
  });

  it('adds a ratio from a date; zero is refused', async () => {
    render(<PointRatioDialog open onOpenChange={() => {}} />);
    const add = screen.getByRole('button', {
      name: 'Add',
    }) as HTMLButtonElement;
    fireEvent.change(screen.getByLabelText('RM per point'), {
      target: { value: '0' },
    });
    expect(add.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('RM per point'), {
      target: { value: '1.35' },
    });
    fireEvent.click(add);
    await waitFor(() =>
      expect(save.mutateAsync).toHaveBeenCalledWith({
        effective_from: '2026-10-01',
        rm_per_point: 1.35,
      }),
    );
  });

  it('edits a row in place and saves the new value with its date', async () => {
    render(<PointRatioDialog open onOpenChange={() => {}} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Edit ratio from 01/01/2026' }),
    );
    const input = screen.getByLabelText(
      'Edit RM per point',
    ) as HTMLInputElement;
    expect(input.value).toBe('1.2');
    const saveRow = screen.getByRole('button', {
      name: 'Save ratio',
    }) as HTMLButtonElement;
    fireEvent.change(input, { target: { value: '0' } });
    expect(saveRow.disabled).toBe(true);
    fireEvent.change(input, { target: { value: '1.25' } });
    // The From date is editable too, and the new one is what is saved.
    const date = screen.getByLabelText('Ratio from') as HTMLInputElement;
    expect(date.value).toBe('2026-01-01');
    fireEvent.change(date, { target: { value: '2026-02-01' } });
    fireEvent.click(saveRow);
    await waitFor(() =>
      expect(update.mutateAsync).toHaveBeenCalledWith({
        id: 'r1',
        effective_from: '2026-02-01',
        rm_per_point: 1.25,
      }),
    );
    await waitFor(() =>
      expect(screen.queryByLabelText('Edit RM per point')).toBeNull(),
    );
  });

  it('cancelling an edit leaves the row as it was', () => {
    render(<PointRatioDialog open onOpenChange={() => {}} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Edit ratio from 01/10/2026' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel edit' }));
    expect(screen.queryByLabelText('Edit RM per point')).toBeNull();
    expect(update.mutateAsync).not.toHaveBeenCalled();
  });

  it('deletes a row through the deferred point_ratio.delete action, no confirm dialog', () => {
    render(<PointRatioDialog open onOpenChange={() => {}} />);
    expect(deferredInput.current).toMatchObject({
      actionKey: 'point_ratio.delete',
      entityType: 'point_ratio',
      surface: 'inline',
    });
    // Deleting refreshes the ratio list and the targets that read it, as Add does.
    expect(deferredInput.current?.invalidateKeys).toEqual(
      expect.arrayContaining([
        ['sales-target-point-ratios'],
        ['sales-targets'],
        ['sales-target'],
      ]),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Delete ratio from 01/10/2026' }),
    );
    expect(deletion.run).toHaveBeenCalledWith({
      id: 'r2',
      subject: 'the ratio from 01/10/2026',
    });
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('shows the countdown in the row being deleted', () => {
    deletion.targetId = 'r2';
    deletion.countdown = <span>Deleting in 10s</span>;
    render(<PointRatioDialog open onOpenChange={() => {}} />);
    expect(screen.getByText('Deleting in 10s')).toBeTruthy();
    expect(
      screen.queryByRole('button', { name: 'Delete ratio from 01/10/2026' }),
    ).toBeNull();
    expect(
      screen.getByRole('button', { name: 'Delete ratio from 01/01/2026' }),
    ).toBeTruthy();
  });
});

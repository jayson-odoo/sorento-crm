/**
 * P7 - the build dialog.
 *
 * The split key is a choice now, so what is pinned here is that the dialog opens on the
 * schedule-area split (the behaviour every earlier build had) and that whatever the user
 * picks reaches the caller. A split silently reverting to area would produce a plausible
 * looking set of drafts cut the wrong way, which is not something the list can show.
 */
import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../_shared/hooks/useProjects', () => ({
  usePurchaseOrders: () => ({
    data: [
      {
        id: 'po-1',
        po_number: 'HQ/26/01/121',
        issuing_party_name: 'Buimaco Sdn Bhd',
        po_date: '2026-01-19',
      },
    ],
    isLoading: false,
    isError: false,
  }),
}));

vi.mock('../../_shared/hooks/useProjectSalesOrders', () => ({
  useScheduleVersions: () => ({
    data: [
      {
        id: 'sched-v1',
        delivery_schedule_id: 'sched-1',
        version_no: 1,
        revision_label: 'R1',
        extraction_state: 'done',
        schedule_date: '2026-03-04',
        confirmed_at: '2026-03-05T00:00:00',
      },
    ],
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    id,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    id?: string;
  }) => (
    <select
      id={id}
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { SalesOrderBuildDialog } from './SalesOrderBuildDialog';
import type { SalesOrderSplitBy } from '../../_shared/types/projectSalesOrder.types';

type BuildInput = {
  poId: string;
  scheduleVersionId: string;
  splitBy: SalesOrderSplitBy;
};

function renderDialog(onBuild: (input: BuildInput) => Promise<unknown>) {
  return render(
    <SalesOrderBuildDialog
      projectId="p1"
      onDone={vi.fn()}
      onBuild={onBuild}
      building={false}
    />,
  );
}

async function pickPair() {
  fireEvent.change(await screen.findByLabelText('Select a purchase order'), {
    target: { value: 'po-1' },
  });
  fireEvent.change(await screen.findByLabelText('Select a schedule version'), {
    target: { value: 'sched-v1' },
  });
}

function confirmBuild() {
  fireEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Build drafts',
    }),
  );
  fireEvent.click(
    within(screen.getByRole('alertdialog')).getByRole('button', {
      name: 'Build drafts',
    }),
  );
}

describe('SalesOrderBuildDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('offers the three splits and opens on the schedule area', async () => {
    renderDialog(vi.fn(async () => undefined));

    const select = (await screen.findByLabelText(
      'Select how to split',
    )) as HTMLSelectElement;
    expect(select.value).toBe('area');
    expect(
      Array.from(select.options)
        .map((option) => option.value)
        .filter(Boolean),
    ).toEqual(['area', 'delivery_date', 'delivery_month']);
    expect(screen.getByText('Split by')).toBeInTheDocument();
  });

  it('builds by schedule area when the split is left alone', async () => {
    const onBuild = vi.fn(async () => undefined);
    renderDialog(onBuild);

    await pickPair();
    confirmBuild();

    await waitFor(() =>
      expect(onBuild).toHaveBeenCalledWith({
        poId: 'po-1',
        scheduleVersionId: 'sched-v1',
        splitBy: 'area',
      }),
    );
  });

  it('passes the chosen split through to the build', async () => {
    const onBuild = vi.fn(async () => undefined);
    renderDialog(onBuild);

    await pickPair();
    fireEvent.change(screen.getByLabelText('Select how to split'), {
      target: { value: 'delivery_month' },
    });
    confirmBuild();

    await waitFor(() =>
      expect(onBuild).toHaveBeenCalledWith({
        poId: 'po-1',
        scheduleVersionId: 'sched-v1',
        splitBy: 'delivery_month',
      }),
    );
  });

  it('names the chosen split in the confirmation', async () => {
    renderDialog(vi.fn(async () => undefined));

    await pickPair();
    fireEvent.change(screen.getByLabelText('Select how to split'), {
      target: { value: 'delivery_date' },
    });
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Build drafts',
      }),
    );

    expect(
      await screen.findByText(/split by delivery date/),
    ).toBeInTheDocument();
  });
});

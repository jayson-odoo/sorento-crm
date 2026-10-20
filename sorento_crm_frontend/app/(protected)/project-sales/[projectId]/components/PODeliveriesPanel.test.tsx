/**
 * PM-SIMPLIFY AC-D1 to AC-D3: one row per area, the date changed where it is shown, and the
 * result said in one toast with Undo. No confirm dialog: the change is reversible.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { POProgress } from '../../_shared/types/poProgress.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const toastSuccess = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: { success: (...args: unknown[]) => toastSuccess(...args), error: vi.fn() },
}));

const changeAreaDate = vi.fn();
vi.mock('../../_shared/services/poProgressService', () => ({
  getPurchaseOrderProgress: vi.fn(),
  changeAreaDate: (...args: unknown[]) => changeAreaDate(...args),
}));

import { PODeliveriesPanel, isoDay } from './PODeliveriesPanel';

const progress: POProgress = {
  purchase_order_id: 'po1',
  schedule_version_id: 'sv2',
  lines: [],
  areas: [
    {
      phase_id: 'ph-cap3',
      area_group: 'Common Area',
      sequence: 3,
      label: 'Part 3',
      delivery_date: '2027-07-22',
      units: '941',
      delivered: '0',
      sales_orders: [{ id: 'so1', provisional_ref: 'PSO-000001', status: 'blocked' }],
    },
  ],
  totals: {
    ordered: '941',
    scheduled: '941',
    delivered: '0',
    outstanding: '941',
    next_delivery_date: '2027-07-22',
    schedule_short_lines: 0,
    schedule_over_lines: 0,
  },
};

function renderPanel(canEdit = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PODeliveriesPanel
        projectId="p1"
        poId="po1"
        progress={progress}
        isLoading={false}
        canEdit={canEdit}
        onUpload={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  changeAreaDate.mockResolvedValue({
    phase_id: 'ph-cap3',
    area_group: 'Common Area',
    label: 'Part 3',
    delivery_date: '2027-08-05',
    previous_date: '2027-07-22',
    moved_lines: 4,
    moved_orders: [{ id: 'so1', provisional_ref: 'PSO-000001' }],
    previous_lines: [{ id: 'l1', delivery_date: '2027-01-07' }],
    amendments: [],
  });
});

describe('PODeliveriesPanel', () => {
  it('lists each area with its date, units, delivered and sales order', async () => {
    renderPanel();

    expect(await screen.findByText('Common Area')).toBeInTheDocument();
    expect(screen.getByText('Part 3')).toBeInTheDocument();
    expect(screen.getByText('0 of 941')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'PSO-000001' })).toHaveAttribute(
      'href',
      '/project-sales/p1/sales-orders/so1',
    );
    expect(screen.getByRole('button', { name: /Upload revised schedule/ })).toBeInTheDocument();
  });

  it('moves the date in two steps and offers Undo with every line it moved', async () => {
    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', { name: /Change the delivery date of Common Area Part 3/ }),
    );
    const box = screen.getByLabelText('Delivery date of Common Area Part 3');
    fireEvent.change(box, { target: { value: '05/08/2027' } });
    // A typed date commits on Enter or blur, never per keystroke.
    expect(changeAreaDate).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: 'Enter' });

    await waitFor(() =>
      expect(changeAreaDate).toHaveBeenCalledWith('ph-cap3', { delivery_date: '2027-08-05' }),
    );
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    const [message, options] = toastSuccess.mock.calls[0];
    expect(message).toMatch(/Common Area, Part 3 moves to/);
    expect(message).toMatch(/PSO-000001 is not published, so their lines take the new date\./);
    expect(message).toMatch(/Nothing published changes\./);
    expect(options.action.label).toBe('Undo');

    options.action.onClick();
    await waitFor(() =>
      expect(changeAreaDate).toHaveBeenLastCalledWith('ph-cap3', {
        delivery_date: '2027-07-22',
        restore_lines: [{ id: 'l1', delivery_date: '2027-01-07' }],
      }),
    );
  });

  it('shows the date read-only to someone who may not edit', async () => {
    renderPanel(false);

    await screen.findByText('Common Area');
    expect(screen.queryByRole('button', { name: /Change the delivery date/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Upload/ })).toBeNull();
  });

  it('formats a local day without moving it through UTC', () => {
    expect(isoDay(new Date(2027, 7, 5))).toBe('2027-08-05');
  });
});

/**
 * P6 - upload (AC-E6, contract section 4).
 *
 * Two things have to hold. The PO is required, because the PO VERSION is what the column totals
 * are reconciled against and a schedule with nothing to check against is useless. And the issuer
 * is asked rather than assumed: on the real documents R2 came from a different company than the
 * one that raised the PO.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '@/lib/toast';
import type { Project } from '../../_shared/types/project.types';
import type { DeliverySchedule } from '../../_shared/types/deliverySchedule.types';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
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

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(''),
}));

const uploadDeliverySchedule = vi.fn();
vi.mock('../../_shared/services/deliveryScheduleService', () => ({
  listDeliverySchedules: vi.fn(),
  listDeliveryScheduleVersions: vi.fn(),
  getDeliveryScheduleVersion: vi.fn(),
  uploadDeliverySchedule: (...args: unknown[]) => uploadDeliverySchedule(...args),
  saveDeliveryScheduleCells: vi.fn(),
  resolveDeliveryScheduleProduct: vi.fn(),
  confirmDeliveryScheduleVersion: vi.fn(),
}));

const listPurchaseOrders = vi.fn();
const listParties = vi.fn();
vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../_shared/services/projectService')>();
  return {
    ...actual,
    listPurchaseOrders: (...args: unknown[]) => listPurchaseOrders(...args),
    listParties: (...args: unknown[]) => listParties(...args),
  };
});

import { DeliveryScheduleUploadDialog } from './DeliveryScheduleUploadDialog';

const project: Project = {
  id: 'p1',
  project_code: 'PRJ-000001',
  title: 'Tuju Residences',
  outcome: 'open',
  is_critical: false,
  brands: [],
  brand_ids: [],
  next_action_overdue: false,
  stale_level: 0,
  is_unattended: false,
  open_task_count: 0,
  can_edit: true,
};

const existing: DeliverySchedule = {
  id: 's1',
  purchase_order_id: 'po1',
  po_number: 'HQ/26/01/121',
  version_count: 1,
  latest_version_id: 'v1',
  latest_version_no: 1,
  latest_revision_label: 'DATE : 4 MARCH 2026',
  issuer_party_label: 'Buimaco Sdn Bhd',
  schedule_date: '2026-03-04',
  extraction_state: 'done',
  reconciled_columns: 29,
  total_columns: 37,
  confirmed_at: '2026-03-05T01:40:00',
};

function renderDialog(schedules: DeliverySchedule[] = []) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onDone = vi.fn();
  const result = render(
    <QueryClientProvider client={client}>
      <DeliveryScheduleUploadDialog
        project={project}
        schedules={schedules}
        onDone={onDone}
      />
    </QueryClientProvider>,
  );
  return { ...result, onDone };
}

const pdf = () => new File(['%PDF-1.6'], 'delivery-schedule-slg-r2.pdf', {
  type: 'application/pdf',
});

beforeEach(() => {
  vi.clearAllMocks();
  listPurchaseOrders.mockResolvedValue([
    {
      id: 'po1',
      project_id: 'p1',
      po_source: 'contractor_direct',
      po_number: 'HQ/26/01/121',
      issuing_party_name: 'Buimaco Sdn Bhd',
      line_count: 52,
      line_total: '1810640.62',
      model_mismatch_count: 0,
      price_mismatch_count: 0,
    },
  ]);
  listParties.mockResolvedValue({
    data: [{ id: 'party-slg', name: 'SLG Construction Sdn Bhd', party_type: 'main_contractor' }],
    pagination: { total: 1, page: 1, limit: 50 },
    empty: false,
  });
  uploadDeliverySchedule.mockResolvedValue({
    delivery_schedule_id: 's1',
    schedule_version_id: 'v2',
    version_no: 2,
    extraction_state: 'queued',
    page_count: 7,
  });
});

describe('DeliveryScheduleUploadDialog', () => {
  it('will not upload without a file', async () => {
    renderDialog();
    await waitFor(() => expect(listPurchaseOrders).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: /^Upload$/ })).toBeDisabled();
  });

  it('picks the only PO rather than making the user confirm the obvious', async () => {
    renderDialog();
    await waitFor(() =>
      expect(screen.getByLabelText(/Purchase order/i)).toHaveTextContent('HQ/26/01/121'),
    );
  });

  it('uploads the file against the PO and opens the review screen', async () => {
    renderDialog();
    await waitFor(() =>
      expect(screen.getByLabelText(/Purchase order/i)).toHaveTextContent('HQ/26/01/121'),
    );

    fireEvent.change(screen.getByLabelText(/Revision label/i), {
      target: { value: 'REVISED 1 - 23/7/2026' },
    });
    fireEvent.change(screen.getByLabelText(/^File/i), {
      target: { files: [pdf()] },
    });

    fireEvent.click(screen.getByRole('button', { name: /^Upload$/ }));

    await waitFor(() => expect(uploadDeliverySchedule).toHaveBeenCalled());
    const [poId, body] = uploadDeliverySchedule.mock.calls[0];
    expect(poId).toBe('po1');
    expect(body.revision_label).toBe('REVISED 1 - 23/7/2026');
    expect(body.file.name).toBe('delivery-schedule-slg-r2.pdf');
    expect(body.delivery_schedule_id).toBeNull();

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/project-sales/p1/delivery-schedules/v2'),
    );
  });

  it('offers the existing schedule so a revision becomes a version of it', async () => {
    renderDialog([existing]);
    await waitFor(() =>
      expect(screen.getByLabelText(/Purchase order/i)).toHaveTextContent('HQ/26/01/121'),
    );

    const revisionOf = screen.getByLabelText(/Revision of/i);
    expect(revisionOf).toHaveTextContent('A schedule we have not seen before');

    fireEvent.click(revisionOf);
    fireEvent.click(await screen.findByText('DATE : 4 MARCH 2026'));

    fireEvent.change(screen.getByLabelText(/^File/i), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole('button', { name: /^Upload$/ }));

    await waitFor(() => expect(uploadDeliverySchedule).toHaveBeenCalled());
    expect(uploadDeliverySchedule.mock.calls[0][1].delivery_schedule_id).toBe('s1');
  });

  it('records an issuer that is not the party who raised the PO', async () => {
    renderDialog();
    await waitFor(() =>
      expect(screen.getByLabelText(/Purchase order/i)).toHaveTextContent('HQ/26/01/121'),
    );

    fireEvent.click(screen.getByLabelText(/Issued by/i));
    fireEvent.click(await screen.findByText('SLG Construction Sdn Bhd'));

    fireEvent.change(screen.getByLabelText(/^File/i), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole('button', { name: /^Upload$/ }));

    await waitFor(() => expect(uploadDeliverySchedule).toHaveBeenCalled());
    expect(uploadDeliverySchedule.mock.calls[0][1].issuer_party_id).toBe('party-slg');
  });

  it('surfaces the duplicate-upload 409 and leaves the dialog open to try a different file', async () => {
    uploadDeliverySchedule.mockRejectedValue(
      new Error(
        'This file is already version 1 of this schedule (uploaded 19/08/2026 07:26). ' +
          'Open that version to read it again, or upload a changed file.',
      ),
    );
    const { onDone } = renderDialog();
    await waitFor(() =>
      expect(screen.getByLabelText(/Purchase order/i)).toHaveTextContent('HQ/26/01/121'),
    );

    fireEvent.change(screen.getByLabelText(/^File/i), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole('button', { name: /^Upload$/ }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'This file is already version 1 of this schedule (uploaded 19/08/2026 07:26). ' +
          'Open that version to read it again, or upload a changed file.',
      ),
    );
    expect(push).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /^Upload$/ })).toBeInTheDocument();
  });

  it('says so when the project has no PO to reconcile against', async () => {
    listPurchaseOrders.mockResolvedValue([]);
    renderDialog();

    fireEvent.click(screen.getByLabelText(/Purchase order/i));
    expect(
      await screen.findByText(/No purchase orders on this project/i),
    ).toBeInTheDocument();
  });
});

/**
 * P6 - DeliverySchedulesPanel (AC-E1, AC-E6, AC-G1).
 *
 * What is worth pinning: the tab answers "which schedule still has a column that does not add
 * up" WITHOUT opening anything, it refuses to offer an upload before a PO exists (a schedule is
 * reconciled against a PO version, so there is nothing to check it against), and a revision is
 * a version of the same schedule rather than a second row.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';
import type {
  DeliverySchedule,
  DeliveryScheduleVersionSummary,
} from '../../_shared/types/deliverySchedule.types';

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
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  // Without this the grid never leaves its skeleton: the real hook fetches saved column
  // order and `isLoading` gates the body rows, and nothing answers that call under jsdom.
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(''),
}));

const listDeliverySchedules = vi.fn();
const listDeliveryScheduleVersions = vi.fn();
vi.mock('../../_shared/services/deliveryScheduleService', () => ({
  listDeliverySchedules: (...args: unknown[]) => listDeliverySchedules(...args),
  listDeliveryScheduleVersions: (...args: unknown[]) =>
    listDeliveryScheduleVersions(...args),
  getDeliveryScheduleVersion: vi.fn(),
  uploadDeliverySchedule: vi.fn(),
  saveDeliveryScheduleCells: vi.fn(),
  resolveDeliveryScheduleProduct: vi.fn(),
  confirmDeliveryScheduleVersion: vi.fn(),
}));

const listPurchaseOrders = vi.fn();
vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../_shared/services/projectService')>();
  return {
    ...actual,
    listPurchaseOrders: (...args: unknown[]) => listPurchaseOrders(...args),
    listParties: vi.fn(async () => ({
      data: [],
      pagination: { total: 0, page: 1, limit: 50 },
      empty: true,
    })),
  };
});

import { DeliverySchedulesPanel } from './DeliverySchedulesPanel';

function project(overrides: Partial<Project> = {}): Project {
  return {
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
    ...overrides,
  };
}

function schedule(overrides: Partial<DeliverySchedule> = {}): DeliverySchedule {
  return {
    id: 's1',
    purchase_order_id: 'po1',
    po_number: 'HQ/26/01/121',
    version_count: 2,
    latest_version_id: 'v2',
    latest_version_no: 2,
    latest_revision_label: 'REVISED 1 - 23/7/2026',
    issuer_party_label: 'SLG Construction Sdn Bhd',
    schedule_date: '2026-07-23',
    extraction_state: 'done',
    reconciled_columns: 35,
    total_columns: 38,
    confirmed_at: null,
    ...overrides,
  };
}

function versionSummary(
  overrides: Partial<DeliveryScheduleVersionSummary> = {},
): DeliveryScheduleVersionSummary {
  return {
    id: 'v2',
    delivery_schedule_id: 's1',
    version_no: 2,
    revision_label: 'REVISED 1 - 23/7/2026',
    issuer_party_label: 'SLG Construction Sdn Bhd',
    schedule_date: '2026-07-23',
    extraction_state: 'done',
    reconciled_columns: 35,
    total_columns: 38,
    confirmed_at: null,
    created_at: '2026-07-23T02:11:00',
    ...overrides,
  };
}

function renderPanel(overrides: Partial<Project> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DeliverySchedulesPanel project={project(overrides)} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listDeliverySchedules.mockResolvedValue([]);
  listDeliveryScheduleVersions.mockResolvedValue([versionSummary()]);
  listPurchaseOrders.mockResolvedValue([
    {
      id: 'po1',
      project_id: 'p1',
      po_source: 'contractor_direct',
      po_number: 'HQ/26/01/121',
      line_count: 52,
      line_total: '1810640.62',
      model_mismatch_count: 0,
      price_mismatch_count: 0,
    },
  ]);
});

describe('DeliverySchedulesPanel', () => {
  it('renders a loading skeleton before anything arrives', () => {
    listDeliverySchedules.mockReturnValue(new Promise(() => {}));
    const { container } = renderPanel();
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it('offers the first upload once a PO exists', async () => {
    renderPanel();
    expect(await screen.findByText(/No delivery schedule yet/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Upload the first schedule/i }),
    ).toBeInTheDocument();
  });

  it('sends the user to the PO first when there is nothing to reconcile against', async () => {
    listPurchaseOrders.mockResolvedValue([]);
    renderPanel();

    // The heading states it; the sentence pointing at the POs tab is gone, and the DISABLED
    // upload button (with its reason on the tooltip) is what stops the user.
    expect(await screen.findByText('No delivery schedule yet')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Upload the first schedule/i }),
    ).toBeNull();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Upload a schedule/i })).toBeDisabled(),
    );
  });

  it('states the error rather than showing an empty tab', async () => {
    listDeliverySchedules.mockRejectedValue(new Error('The service did not answer'));
    renderPanel();

    // The grid states the failure in the message the server gave, rather than a heading of
    // its own plus the message underneath.
    expect(await screen.findByText(/The service did not answer/i)).toBeInTheDocument();
  });

  it('reads a schedule without opening it: PO, revision, issuer and what is left to reconcile', async () => {
    listDeliverySchedules.mockResolvedValue([schedule()]);
    renderPanel();

    expect(await screen.findAllByText('HQ/26/01/121')).not.toHaveLength(0);
    expect(screen.getByText('35 of 38 columns reconciled')).toBeInTheDocument();
    expect(screen.getByText('3 columns to reconcile')).toBeInTheDocument();
    expect(screen.getByText('Not confirmed')).toBeInTheDocument();
    expect(screen.getByText('v2 of 2')).toBeInTheDocument();
    // Its own "Issued by" column, so the name stands alone.
    expect(
      screen.getByText('SLG Construction Sdn Bhd'),
    ).toBeInTheDocument();
  });

  it('says so plainly when every column agrees and the schedule is confirmed', async () => {
    listDeliverySchedules.mockResolvedValue([
      schedule({ reconciled_columns: 38, total_columns: 38, confirmed_at: '2026-07-24T01:05:00' }),
    ]);
    renderPanel();

    expect(await screen.findByText('All 38 columns reconciled')).toBeInTheDocument();
    // Twice on purpose: the badge on the row, and the column in the version history below it.
    expect(screen.getAllByText('Confirmed').length).toBeGreaterThan(0);
    expect(screen.queryByText(/columns to reconcile/i)).toBeNull();
  });

  it('opens the first schedule on arrival and lists its versions', async () => {
    listDeliverySchedules.mockResolvedValue([schedule()]);
    renderPanel();

    await screen.findByText('v2 of 2');
    await waitFor(() => expect(listDeliveryScheduleVersions).toHaveBeenCalledWith('s1'));
  });

  it('links a schedule to its own review screen rather than reviewing it in the tab', async () => {
    listDeliverySchedules.mockResolvedValue([schedule()]);
    renderPanel();

    const review = await screen.findByRole('link', { name: /^Review$/ });
    expect(review).toHaveAttribute(
      'href',
      '/project-sales/p1/delivery-schedules/v2',
    );
  });

  it('hides every write affordance on a project the user cannot edit', async () => {
    listDeliverySchedules.mockResolvedValue([schedule()]);
    renderPanel({ can_edit: false });

    await screen.findByText('v2 of 2');
    expect(screen.queryByRole('button', { name: /Upload a schedule/i })).toBeNull();
  });

  it('opens the upload dialog from the header', async () => {
    listDeliverySchedules.mockResolvedValue([schedule()]);
    renderPanel();

    const trigger = await screen.findByRole('button', { name: /Upload a schedule/i });
    // Enabled only once the PO list lands, and a click on a disabled button does nothing.
    await waitFor(() => expect(trigger).toBeEnabled());
    fireEvent.click(trigger);

    expect(await screen.findByText('Upload a delivery schedule')).toBeInTheDocument();
    // A revision is a version of the SAME schedule, so the existing one is offerable.
    expect(screen.getByLabelText(/Revision of/i)).toBeInTheDocument();
  });
});

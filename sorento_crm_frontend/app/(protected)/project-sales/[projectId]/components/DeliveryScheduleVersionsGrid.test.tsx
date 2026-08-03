/**
 * P6 - the version history (AC-G1).
 *
 * Every revision is a new version of the same commitment, so what matters is that an older
 * version stays openable and that each row says who issued it and when. "What did they ask for
 * before the delay" is the question versioning exists to answer.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(''),
}));

// Without this the shared DataGrid sits in its column-preferences fetch forever and renders
// skeleton rows instead of data.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const listDeliveryScheduleVersions = vi.fn();
vi.mock('../../_shared/services/deliveryScheduleService', () => ({
  listDeliverySchedules: vi.fn(),
  listDeliveryScheduleVersions: (...args: unknown[]) =>
    listDeliveryScheduleVersions(...args),
  getDeliveryScheduleVersion: vi.fn(),
  uploadDeliverySchedule: vi.fn(),
  saveDeliveryScheduleCells: vi.fn(),
  resolveDeliveryScheduleProduct: vi.fn(),
  confirmDeliveryScheduleVersion: vi.fn(),
}));

import { DeliveryScheduleVersionsGrid } from './DeliveryScheduleVersionsGrid';

const schedule: DeliverySchedule = {
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
};

function summary(
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

function renderGrid() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DeliveryScheduleVersionsGrid projectId="p1" schedule={schedule} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listDeliveryScheduleVersions.mockResolvedValue([]);
});

describe('DeliveryScheduleVersionsGrid', () => {
  it('lists every version with its label, issuer and dates', async () => {
    listDeliveryScheduleVersions.mockResolvedValue([
      summary(),
      summary({
        id: 'v1',
        version_no: 1,
        revision_label: 'DATE : 4 MARCH 2026',
        issuer_party_label: 'Buimaco Sdn Bhd',
        schedule_date: '2026-03-04',
        reconciled_columns: 38,
        confirmed_at: '2026-03-05T01:40:00',
      }),
    ]);
    renderGrid();

    expect(await screen.findByText('v2')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.getByText('REVISED 1 - 23/7/2026')).toBeInTheDocument();
    expect(screen.getByText('DATE : 4 MARCH 2026')).toBeInTheDocument();
    expect(screen.getByText('Buimaco Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('35 of 38 columns reconciled')).toBeInTheDocument();
    expect(screen.getByText('All 38 columns reconciled')).toBeInTheDocument();
  });

  it('lets any version be opened, not only the latest', async () => {
    listDeliveryScheduleVersions.mockResolvedValue([
      summary(),
      summary({ id: 'v1', version_no: 1 }),
    ]);
    renderGrid();

    const links = await screen.findAllByRole('link', { name: 'Open' });
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/project-sales/p1/delivery-schedules/v2',
      '/project-sales/p1/delivery-schedules/v1',
    ]);
  });

  it('says what is missing rather than rendering an empty table', async () => {
    renderGrid();
    expect(await screen.findByText(/No versions on record/i)).toBeInTheDocument();
  });

  it('states a load failure', async () => {
    listDeliveryScheduleVersions.mockRejectedValue(new Error('nope'));
    renderGrid();
    expect(
      await screen.findByText(/version history could not be loaded/i),
    ).toBeInTheDocument();
  });

  it('shows a dash for an unknown value rather than a blank cell', async () => {
    listDeliveryScheduleVersions.mockResolvedValue([
      summary({ revision_label: null, issuer_party_label: null, schedule_date: null }),
    ]);
    renderGrid();

    expect(await screen.findByText('No revision label')).toBeInTheDocument();
    expect(screen.getByText('-')).toBeInTheDocument();
    expect(screen.getByText('Not dated')).toBeInTheDocument();
    expect(screen.getByText('Not yet')).toBeInTheDocument();
  });
});

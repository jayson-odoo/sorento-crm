/**
 * P6 - the `?demo=` toggle.
 *
 * It exists so every state of this screen can be looked at without a backend, and its one rule
 * is that it must not become a second code path: the components render the same way, no request
 * is made, and dropping the parameter goes back to live data. That rule is what is tested here,
 * along with the states that are hard to reach on demand.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

let search = '';
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/delivery-schedules/demo-version-2',
  useSearchParams: () => new URLSearchParams(search),
}));

const getDeliveryScheduleVersion = vi.fn();
vi.mock('../../../_shared/services/deliveryScheduleService', () => ({
  listDeliverySchedules: vi.fn(),
  listDeliveryScheduleVersions: vi.fn(),
  uploadDeliverySchedule: vi.fn(),
  getDeliveryScheduleVersion: (...args: unknown[]) => getDeliveryScheduleVersion(...args),
  saveDeliveryScheduleCells: vi.fn(),
  resolveDeliveryScheduleProduct: vi.fn(),
  confirmDeliveryScheduleVersion: vi.fn(),
}));

const getProject = vi.fn();
vi.mock('../../../_shared/services/projectService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../_shared/services/projectService')>();
  return { ...actual, getProject: (...args: unknown[]) => getProject(...args) };
});

vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: vi.fn(async () => []),
}));

import { DeliveryScheduleReviewClient } from '../components/DeliveryScheduleReviewClient';

function renderReview() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DeliveryScheduleReviewClient projectId="p1" versionId="demo-version-2" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  search = '';
});

describe('the ?demo= toggle', () => {
  it('renders the fixture without asking the backend for anything', async () => {
    search = 'demo=data';
    renderReview();

    expect(
      await screen.findByRole('heading', { name: /Delivery schedule for HQ\/26\/01\/121/ }),
    ).toBeInTheDocument();
    // Six columns, four of which reconcile on the first pass, as measured on the real document.
    expect(screen.getByText('4 of 6 columns reconciled')).toBeInTheDocument();
    expect(getDeliveryScheduleVersion).not.toHaveBeenCalled();
    expect(getProject).not.toHaveBeenCalled();
  });

  it('reaches the partial extraction state, which is otherwise hard to produce on demand', async () => {
    search = 'demo=partial';
    renderReview();

    expect(await screen.findByText('Only 5 of 7 pages were read')).toBeInTheDocument();
    expect(screen.getByTestId('schedule-matrix')).toBeInTheDocument();
  });

  it('reaches a confirmed version where every column agrees', async () => {
    search = 'demo=confirmed';
    renderReview();

    expect(await screen.findByText(/Confirmed .* by Eling Tan/)).toBeInTheDocument();
    expect(screen.getByText('All 6 columns reconciled')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Confirm$/ })).toBeNull();
  });

  it('falls back to the live query when the parameter is not a known state', async () => {
    search = 'demo=nonsense';
    getDeliveryScheduleVersion.mockReturnValue(new Promise(() => {}));
    getProject.mockReturnValue(new Promise(() => {}));
    renderReview();

    expect(getDeliveryScheduleVersion).toHaveBeenCalledWith('demo-version-2');
  });
});

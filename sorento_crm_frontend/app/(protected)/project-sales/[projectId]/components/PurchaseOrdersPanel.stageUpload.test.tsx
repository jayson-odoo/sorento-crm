/**
 * PROJECT-STAGE-ACTIONS: the PO received stage button lands on the PO tab with
 * `upload=po`, and the panel opens its existing "Upload a customer PO" dialog straight away.
 * The param is dropped once the dialog is open, so cancelling leaves the user on the PO tab and
 * a refresh does not reopen it.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const replace = vi.fn();
let params = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => params,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/projectService')>();
  return {
    ...actual,
    listPurchaseOrders: vi.fn(async () => []),
    listPurchaseOrderLines: vi.fn(async () => []),
    listSamples: vi.fn(async () => []),
    listDeliverySchedules: vi.fn(async () => []),
    listProjectSalesOrders: vi.fn(async () => ({ data: [], pagination: { total: 0 } })),
  };
});

// The dialog itself has its own tests; here only "is it open, and what does Cancel do" matters.
vi.mock('./POIntakeUploadDialog', () => ({
  POIntakeUploadDialog: ({ onDone }: { onDone: () => void }) => (
    <div role="dialog" aria-label="Upload a customer PO">
      <button type="button" onClick={onDone}>
        Cancel
      </button>
    </div>
  ),
}));

import { PurchaseOrdersPanel } from './PurchaseOrdersPanel';

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Test',
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

function renderPanel(overrides: Partial<Project> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseOrdersPanel project={project(overrides)} />
    </QueryClientProvider>,
  );
}

describe('PurchaseOrdersPanel opened by the PO received stage button', () => {
  beforeEach(() => {
    replace.mockReset();
    params = new URLSearchParams();
  });

  it('opens the upload dialog at once on ?upload=po', () => {
    params = new URLSearchParams('tab=orders&upload=po');
    renderPanel();
    expect(screen.getByRole('dialog', { name: 'Upload a customer PO' })).toBeTruthy();
  });

  it('drops upload=po from the URL and keeps the PO tab', () => {
    params = new URLSearchParams('tab=orders&upload=po');
    renderPanel();
    expect(replace).toHaveBeenCalledWith('/project-sales/p1?tab=orders', { scroll: false });
  });

  it('Cancel closes the dialog and leaves the PO tab in place', () => {
    params = new URLSearchParams('tab=orders&upload=po');
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog', { name: 'Upload a customer PO' })).toBeNull();
    expect(screen.getByText('No PO received yet')).toBeTruthy();
  });

  it('opens nothing without the param', () => {
    params = new URLSearchParams('tab=orders');
    renderPanel();
    expect(screen.queryByRole('dialog', { name: 'Upload a customer PO' })).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it('opens nothing for a reader who cannot upload', () => {
    params = new URLSearchParams('tab=orders&upload=po');
    renderPanel({ can_edit: false });
    expect(screen.queryByRole('dialog', { name: 'Upload a customer PO' })).toBeNull();
  });
});

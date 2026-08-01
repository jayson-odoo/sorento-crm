/**
 * P4 - re-entering a review from the POs tab.
 *
 * The case worth pinning is the one that is easy to get wrong: when the backend has no
 * version list endpoint yet, the strip must say NOTHING rather than "no documents". A
 * confident wrong answer here would send someone off to re-upload a PO they already uploaded.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { POVersionSummary } from '../../_shared/types/poIntake.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => ({ get: () => null }),
}));

const listPOVersions = vi.fn();
vi.mock('../../_shared/services/poIntakeService', () => ({
  listPOVersions: (...args: unknown[]) => listPOVersions(...args),
  uploadPurchaseOrderDocument: vi.fn(),
  getPOVersion: vi.fn(),
  updatePOVersionLine: vi.fn(),
  updatePOVersionHeader: vi.fn(),
  confirmPOVersion: vi.fn(),
  approvePurchaseOrder: vi.fn(),
  countersignPurchaseOrder: vi.fn(),
  acceptPOAnnotation: vi.fn(),
  editPOAnnotation: vi.fn(),
  rejectPOAnnotation: vi.fn(),
}));

import { POIntakeVersionsStrip } from './POIntakeVersionsStrip';

function renderStrip(canEdit = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <POIntakeVersionsStrip
        projectId="p1"
        poId="po1"
        canEdit={canEdit}
        onUpload={() => {}}
      />
    </QueryClientProvider>,
  );
}

function summary(overrides: Partial<POVersionSummary> = {}): POVersionSummary {
  return {
    id: 'v1',
    purchase_order_id: 'po1',
    version_no: 1,
    extraction_state: 'done',
    confirmed_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('POIntakeVersionsStrip', () => {
  it('shows a placeholder while it is reading', () => {
    listPOVersions.mockReturnValue(new Promise(() => {}));

    renderStrip();

    expect(document.querySelectorAll('[data-slot="skeleton"]').length).toBe(1);
  });

  it('says nothing at all when the endpoint does not exist yet', async () => {
    listPOVersions.mockResolvedValue(null);

    const { container } = renderStrip();

    await waitFor(() =>
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBe(0),
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('offers the upload when the PO genuinely has no scan', async () => {
    listPOVersions.mockResolvedValue([]);

    renderStrip();

    expect(await screen.findByText(/No scan of this PO has been uploaded/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Upload the document/i }),
    ).toBeInTheDocument();
  });

  it('lists newest first and links each one to its review', async () => {
    listPOVersions.mockResolvedValue([
      summary(),
      summary({ id: 'v2', version_no: 2, extraction_state: 'queued' }),
    ]);

    renderStrip();

    const links = await screen.findAllByRole('link');
    expect(links[0]).toHaveAttribute('href', '/project-sales/p1/purchase-orders/v2');
    expect(links[1]).toHaveAttribute('href', '/project-sales/p1/purchase-orders/v1');
    expect(screen.getByText('Version 2')).toBeInTheDocument();
    expect(screen.getByText('Waiting to be read')).toBeInTheDocument();
    expect(screen.getAllByText('Not confirmed')).toHaveLength(2);
  });

  it('says a version is confirmed with the time on it', async () => {
    listPOVersions.mockResolvedValue([
      summary({ confirmed_at: '2026-05-15T03:02:00' }),
    ]);

    renderStrip();

    expect(await screen.findByText(/Confirmed /)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open' })).toBeInTheDocument();
  });

  it('renders a row that carries only the documented subset, without an empty badge', async () => {
    listPOVersions.mockResolvedValue([
      { id: 'v1', version_no: 1, confirmed_at: null } as POVersionSummary,
    ]);

    renderStrip();

    expect(await screen.findByText('Version 1')).toBeInTheDocument();
    expect(screen.queryByText('Read')).toBeNull();
    expect(screen.getByRole('link', { name: /Review what we read/i })).toBeInTheDocument();
  });

  it('offers a reader no upload', async () => {
    listPOVersions.mockResolvedValue([]);

    renderStrip(false);

    expect(await screen.findByText(/No scan of this PO has been uploaded/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Upload the document/i })).toBeNull();
  });
});

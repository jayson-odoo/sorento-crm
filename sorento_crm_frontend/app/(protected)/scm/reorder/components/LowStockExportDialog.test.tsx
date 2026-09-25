/**
 * PLAN-low-stock-export-split-25sep (#1229) - LowStockExportDialog (AC-16, AC-16b).
 *
 * Test list items 19: default None selected and resets on reopen; radio changes; the
 * "N rows, M sheets" preview line doubles the group count and reads 2 under None; "..."
 * while loading; hidden on a rejected preview with Export still enabled.
 *
 * Only `getLowStockPreview` (the network-shaped read) is mocked, same pattern as
 * `ReorderPlanView.lowStock.test.tsx` - `previewLowStockExport`, the pure doubling
 * function, is left REAL, and the dialog's own `useLowStockPreview` hook runs for real
 * against a real `QueryClient`.
 *
 * WRITTEN BEFORE ANY BACKEND CODE EXISTS FOR THIS SLICE - this file exercises Phase 1
 * frontend code only (`LowStockExportDialog.tsx`, `summaryOrderService.ts`,
 * `useSummaryOrder.ts` are already built), so every test here is expected to be GREEN,
 * not red. It is the dialog's own coverage, captured now so the coder does not have to
 * write it later.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getLowStockPreview = vi.fn();
// `previewLowStockExport` is kept as the REAL (pure) export - only the network-shaped
// `getLowStockPreview` is stubbed, so the doubling math under test is the module's own.
vi.mock('../services/summaryOrderService', async () => {
  const actual = await vi.importActual<typeof import('../services/summaryOrderService')>(
    '../services/summaryOrderService',
  );
  return {
    ...actual,
    getLowStockPreview: (...args: unknown[]) => getLowStockPreview(...args),
  };
});

import { LowStockExportDialog } from './LowStockExportDialog';

const PREVIEW = {
  rows: 100,
  sheet_counts: { supplier: 5, category: 3, supplier_category: 8 },
};

function Wrapper({
  queryClient,
  open,
  onOpenChange,
  onExport,
  pending,
}: {
  queryClient: QueryClient;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onExport: (split: string) => void;
  pending: boolean;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <LowStockExportDialog
        open={open}
        onOpenChange={onOpenChange}
        runId="run-1"
        onExport={onExport}
        pending={pending}
      />
    </QueryClientProvider>
  );
}

function renderDialog(overrides: { open?: boolean; pending?: boolean } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onOpenChange = vi.fn();
  const onExport = vi.fn();
  const utils = render(
    <Wrapper
      queryClient={queryClient}
      open={overrides.open ?? true}
      onOpenChange={onOpenChange}
      onExport={onExport}
      pending={overrides.pending ?? false}
    />,
  );
  return { ...utils, queryClient, onOpenChange, onExport };
}

beforeEach(() => {
  getLowStockPreview.mockReset();
  getLowStockPreview.mockResolvedValue(PREVIEW);
});

describe('LowStockExportDialog - default and reset (AC-16)', () => {
  it('selects None by default, and resets to None when closed then reopened after a '
    + 'different pick', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onExport = vi.fn();
    const { rerender } = render(
      <Wrapper queryClient={queryClient} open onOpenChange={() => {}} onExport={onExport}
        pending={false} />,
    );
    const user = userEvent.setup();

    expect(await screen.findByRole('radio', { name: 'None' })).toBeChecked();

    await user.click(screen.getByRole('radio', { name: 'Supplier' }));
    expect(screen.getByRole('radio', { name: 'Supplier' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'None' })).not.toBeChecked();

    // Close, then reopen - the SAME dialog instance, split must fall back to None.
    rerender(
      <Wrapper queryClient={queryClient} open={false} onOpenChange={() => {}}
        onExport={onExport} pending={false} />,
    );
    rerender(
      <Wrapper queryClient={queryClient} open onOpenChange={() => {}} onExport={onExport}
        pending={false} />,
    );

    expect(await screen.findByRole('radio', { name: 'None' })).toBeChecked();
  });
});

describe('LowStockExportDialog - radio changes and the preview line (AC-16b)', () => {
  it('reads "100 rows, 2 sheets" under None, one fetch only, no refetch on radio change',
    async () => {
    renderDialog();
    const user = userEvent.setup();

    expect(await screen.findByText('100 rows, 2 sheets')).toBeInTheDocument();
    expect(getLowStockPreview).toHaveBeenCalledTimes(1);
    expect(getLowStockPreview).toHaveBeenCalledWith('run-1');

    // Supplier: sheet_counts.supplier (5) doubled to 10 sheets - recomputed LOCALLY.
    await user.click(screen.getByRole('radio', { name: 'Supplier' }));
    expect(await screen.findByText('100 rows, 10 sheets')).toBeInTheDocument();

    // Category: sheet_counts.category (3) doubled to 6.
    await user.click(screen.getByRole('radio', { name: 'Category' }));
    expect(await screen.findByText('100 rows, 6 sheets')).toBeInTheDocument();

    // Supplier x Category: sheet_counts.supplier_category (8) doubled to 16.
    await user.click(screen.getByRole('radio', { name: 'Supplier x Category' }));
    expect(await screen.findByText('100 rows, 16 sheets')).toBeInTheDocument();

    // Back to None: 2 sheets again, still one fetch total.
    await user.click(screen.getByRole('radio', { name: 'None' }));
    expect(await screen.findByText('100 rows, 2 sheets')).toBeInTheDocument();
    expect(getLowStockPreview).toHaveBeenCalledTimes(1);
  });
});

describe('LowStockExportDialog - loading and error states (AC-16b)', () => {
  it('shows "..." while the preview is loading', async () => {
    getLowStockPreview.mockReturnValue(new Promise(() => {})); // never resolves
    renderDialog();

    expect(await screen.findByText('...')).toBeInTheDocument();
    expect(screen.queryByText(/rows,/)).not.toBeInTheDocument();
  });

  it('hides the preview line on a rejected preview, and leaves Export enabled', async () => {
    getLowStockPreview.mockRejectedValue(new Error('failed'));
    renderDialog();

    await waitFor(() => expect(screen.queryByText('...')).not.toBeInTheDocument());
    expect(screen.queryByText(/rows,/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export' })).not.toBeDisabled();
  });
});

describe('LowStockExportDialog - Export (AC-16/AC-19)', () => {
  it('calls onExport with the chosen split', async () => {
    const { onExport } = renderDialog();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('radio', { name: 'Supplier' }));
    await user.click(screen.getByRole('button', { name: 'Export' }));

    expect(onExport).toHaveBeenCalledWith('supplier');
  });

  it('disables Export and reads "Starting…" while pending', async () => {
    renderDialog({ pending: true });

    const exportButton = await screen.findByRole('button', { name: 'Starting…' });
    expect(exportButton).toBeDisabled();
  });
});

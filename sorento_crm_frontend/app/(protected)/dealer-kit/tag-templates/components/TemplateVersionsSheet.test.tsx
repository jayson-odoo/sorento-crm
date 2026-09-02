/**
 * Versions sheet (S5, AC-S5-6): newest-first list, View is immediate, and so
 * (B2 captain ruling, 2 Sep) is Restore - no confirmation dialog. The host
 * owns the undo-toast safety net; this component only disables the row
 * being restored while `onRestore` is in flight.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../services/tagTemplateService', () => ({
  listTemplateVersions: vi.fn(),
}));

import { listTemplateVersions } from '../../services/tagTemplateService';
import { TemplateVersionsSheet } from './TemplateVersionsSheet';

const mockList = vi.mocked(listTemplateVersions);

function versionsFixture() {
  return [
    {
      id: 'v2',
      template_id: 't1',
      version_no: 2,
      note: 'Bigger price badge',
      created_by: 'user-1',
      created_by_name: 'Marketing Mei',
      created_at: '2026-09-01T02:00:00Z',
    },
    {
      id: 'v1',
      template_id: 't1',
      version_no: 1,
      note: null,
      created_by: 'user-1',
      created_by_name: 'Marketing Mei',
      created_at: '2026-08-20T02:00:00Z',
    },
  ];
}

beforeEach(() => {
  vi.clearAllMocks();
  mockList.mockResolvedValue(versionsFixture());
});

function renderSheet(overrides: Partial<React.ComponentProps<typeof TemplateVersionsSheet>> = {}) {
  return render(
    <TemplateVersionsSheet
      templateId="t1"
      open
      onOpenChange={vi.fn()}
      liveVersionNo={2}
      onView={vi.fn()}
      onRestore={vi.fn().mockResolvedValue(undefined)}
      {...overrides}
    />,
  );
}

it('lists versions newest-first with number, note, author, time', async () => {
  renderSheet();

  await waitFor(() => expect(screen.getByText('Version 2')).toBeInTheDocument());
  const rows = screen.getAllByText(/^Version \d$/);
  expect(rows.map((r) => r.textContent)).toEqual(['Version 2', 'Version 1']);
  expect(screen.getByText('Bigger price badge')).toBeInTheDocument();
  expect(screen.getAllByText(/Marketing Mei/).length).toBeGreaterThan(0);
});

it('badges the version matching the live pointer', async () => {
  renderSheet({ liveVersionNo: 2 });

  await waitFor(() => expect(screen.getByText('Live')).toBeInTheDocument());
});

it('View fires immediately, no confirmation needed', async () => {
  const onView = vi.fn();
  renderSheet({ onView });

  await waitFor(() => expect(screen.getByText('Version 1')).toBeInTheDocument());
  fireEvent.click(screen.getAllByText('View')[1]); // v1's row

  expect(onView).toHaveBeenCalledWith('v1', 1);
});

it('Restore fires immediately, no confirmation needed (B2)', async () => {
  const onRestore = vi.fn().mockResolvedValue(undefined);
  renderSheet({ onRestore });

  await waitFor(() => expect(screen.getByText('Version 1')).toBeInTheDocument());
  fireEvent.click(screen.getAllByText('Restore')[1]); // v1's row

  await waitFor(() => expect(onRestore).toHaveBeenCalledWith('v1'));
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
});

it('disables only the restoring row while onRestore is in flight', async () => {
  let resolveRestore: () => void = () => {};
  const onRestore = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        resolveRestore = resolve;
      }),
  );
  renderSheet({ onRestore });

  await waitFor(() => expect(screen.getByText('Version 1')).toBeInTheDocument());
  const restoreButtons = screen.getAllByText(/Restore/);
  fireEvent.click(restoreButtons[1]); // v1's row

  await waitFor(() => expect(screen.getByText('Restoring...')).toBeInTheDocument());
  // v2's row is untouched - still says "Restore", not disabled.
  expect(screen.getAllByText('Restore')[0]).not.toBeDisabled();

  resolveRestore();
  await waitFor(() => expect(screen.queryByText('Restoring...')).not.toBeInTheDocument());
});

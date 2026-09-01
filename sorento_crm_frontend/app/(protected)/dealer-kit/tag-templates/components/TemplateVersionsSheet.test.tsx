/**
 * Versions sheet (S5, AC-S5-6): newest-first list, View is immediate, Restore
 * is gated behind a confirm - it overwrites the draft, so the same click
 * pattern as `VersionHistory`'s rollback confirm applies here.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

it('Restore asks for confirmation before calling onRestore', async () => {
  const onRestore = vi.fn().mockResolvedValue(undefined);
  renderSheet({ onRestore });

  await waitFor(() => expect(screen.getByText('Version 1')).toBeInTheDocument());
  fireEvent.click(screen.getAllByText('Restore')[1]); // v1's row

  // The confirm dialog is up, and onRestore has NOT fired yet.
  expect(await screen.findByText('Restore version 1?')).toBeInTheDocument();
  expect(onRestore).not.toHaveBeenCalled();

  const dialog = within(screen.getByRole('alertdialog'));
  fireEvent.click(dialog.getByRole('button', { name: 'Restore' }));

  await waitFor(() => expect(onRestore).toHaveBeenCalledWith('v1'));
});

it('cancelling the confirm never calls onRestore', async () => {
  const onRestore = vi.fn();
  renderSheet({ onRestore });

  await waitFor(() => expect(screen.getByText('Version 1')).toBeInTheDocument());
  fireEvent.click(screen.getAllByText('Restore')[1]);
  expect(await screen.findByText('Restore version 1?')).toBeInTheDocument();

  fireEvent.click(screen.getByText('Cancel'));

  await waitFor(() =>
    expect(screen.queryByText('Restore version 1?')).not.toBeInTheDocument(),
  );
  expect(onRestore).not.toHaveBeenCalled();
});

/**
 * PROJECT-OUTCOME-SINGLE FE1 (fix round 1, B2): a drop onto the Lost column asks for a reason
 * first. The dialog is mounted at the top of the page, not inside the Filters popover, so it
 * shows while no popover is open. Nothing moves until Save.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn();
Element.prototype.setPointerCapture = vi.fn();
Element.prototype.releasePointerCapture = vi.fn();

const listProjects = vi.fn();
const changeProjectStatus = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/pipeline',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/app/(protected)/project-sales/_shared/hooks/useProjectStatusGraph', () => ({
  useProjectStatusGraph: () => ({
    isLoading: false,
    data: {
      statuses: [
        { id: 's-quoted', key: 'quoted', label: 'Quoted', sort_order: 1, is_active: true },
        { id: 's-lost', key: 'lost', label: 'Lost', sort_order: 2, is_active: true },
      ],
    },
  }),
}));

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/projectService')>();
  return {
    ...actual,
    listProjects: (...args: unknown[]) => listProjects(...args),
    listParties: vi.fn(async () => ({ data: [], pagination: { total: 0, page: 1, limit: 200 } })),
    listProjectTypes: vi.fn(async () => []),
    listProjectTemplates: vi.fn(async () => []),
    previewClashes: vi.fn(async () => ({ candidates: [] })),
    changeProjectStatus: (...args: unknown[]) => changeProjectStatus(...args),
  };
});

vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../_shared/hooks/useProjects')>()),
  useQuotationLossReasons: () => ({ data: [{ value: 'price', label: 'Price' }] }),
}));

// The board's own drag-and-drop has its tests; here a button stands in for the drop.
vi.mock('./PipelineBoard', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./PipelineBoard')>()),
  PipelineBoard: ({
    onMove,
    projects,
  }: {
    onMove: (projectId: string, toStatusId: string) => void;
    projects: { title: string }[];
  }) =>
    // Rendered only once the rows have loaded, so a click always finds its project.
    projects.length ? (
      <button type="button" onClick={() => onMove('p1', 's-lost')}>
        drop on Lost
      </button>
    ) : null,
}));

const granted = new Set(['projects.projects.edit', 'projects.projects.view']);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => granted.has(s)),
  usePermissions: () => ({
    permissions: [...granted],
    permissionSet: granted,
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: () => <div />,
}));

import { PipelineClient } from './PipelineClient';

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PipelineClient />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  listProjects.mockResolvedValue({
    data: [
      {
        id: 'p1',
        project_code: 'PRJ-000001',
        title: 'Menara Test',
        outcome: 'open',
        status_id: 's-quoted',
        status_key: 'quoted',
        can_edit: true,
        open_task_count: 0,
      } as Project,
    ],
    pagination: { total: 1, page: 1, limit: 200 },
  });
  changeProjectStatus.mockResolvedValue({ id: 'p1', status_label: 'Lost' });
});

describe('PipelineClient: a drop onto the Lost column', () => {
  it('opens the reason dialog with no Filters popover open, and moves nothing yet', async () => {
    renderClient();

    fireEvent.click(await screen.findByRole('button', { name: 'drop on Lost' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(changeProjectStatus).not.toHaveBeenCalled();
  });

  it('Save sends the move with the loss reason', async () => {
    renderClient();
    fireEvent.click(await screen.findByRole('button', { name: 'drop on Lost' }));
    const dialog = await screen.findByRole('dialog');

    fireEvent.change(within(dialog).getByRole('combobox'), { target: { value: 'price' } });
    const save = within(dialog).getByRole('button', { name: 'Save' });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);

    await waitFor(() => expect(changeProjectStatus).toHaveBeenCalledTimes(1));
    expect(changeProjectStatus).toHaveBeenCalledWith('p1', 's-lost', 'price');
  });

  it('Cancel closes it and moves nothing', async () => {
    renderClient();
    fireEvent.click(await screen.findByRole('button', { name: 'drop on Lost' }));
    const dialog = await screen.findByRole('dialog');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(changeProjectStatus).not.toHaveBeenCalled();
  });
});

/**
 * S2b - TemplateChecklistPanel (AC-N10, AC-N11).
 *
 * Two things must be unmistakable on this screen, because getting either wrong loses
 * data or confuses the admin about what they just changed:
 *   - editing the template does NOT reach into projects already registered
 *   - a checklist item already copied somewhere cannot be deleted, only deactivated
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectTemplate, ProjectTemplateTask } from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listTemplateTasks = vi.fn();
const deleteTemplateTask = vi.fn();
const updateTemplateTask = vi.fn();

vi.mock('../../_shared/services/projectService', () => ({
  listTemplateTasks: (...args: unknown[]) => listTemplateTasks(...args),
  createTemplateTask: vi.fn(),
  updateTemplateTask: (...args: unknown[]) => updateTemplateTask(...args),
  deleteTemplateTask: (...args: unknown[]) => deleteTemplateTask(...args),
  listProjectTasks: vi.fn(),
  createProjectTask: vi.fn(),
  updateProjectTask: vi.fn(),
  changeTaskStatus: vi.fn(),
  deleteProjectTask: vi.fn(),
  getTaskHistory: vi.fn(),
  listMyTasks: vi.fn(),
  listProjects: vi.fn(),
  getProject: vi.fn(),
  listProjectTypes: vi.fn(),
  listProjectTemplates: vi.fn(),
  listParties: vi.fn(),
  listStakeholders: vi.fn(),
  listCollaborators: vi.fn(),
  listTakeoverRequests: vi.fn(),
  previewClashes: vi.fn(),
  registerProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  changeProjectStatus: vi.fn(),
  addStakeholder: vi.fn(),
  updateStakeholder: vi.fn(),
  removeStakeholder: vi.fn(),
  createParty: vi.fn(),
  updateParty: vi.fn(),
  deleteParty: vi.fn(),
  createTakeoverRequest: vi.fn(),
  decideTakeoverRequest: vi.fn(),
  createProjectType: vi.fn(),
  updateProjectType: vi.fn(),
  deleteProjectType: vi.fn(),
  createProjectTemplate: vi.fn(),
  updateProjectTemplate: vi.fn(),
  deleteProjectTemplate: vi.fn(),
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
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { TemplateChecklistPanel } from './TemplateChecklistPanel';

const TEMPLATE: ProjectTemplate = {
  id: 'tpl-1',
  type_id: 'type-1',
  name: 'Refurbishment',
  is_active: true,
  roles: [],
  has_forked_status_graph: false,
};

function item(overrides: Partial<ProjectTemplateTask> = {}): ProjectTemplateTask {
  return {
    id: 'ti-1',
    template_id: 'tpl-1',
    name: 'Checklist item',
    task_phase: 'pursuit',
    sort_order: 0,
    is_active: true,
    in_use_count: 0,
    ...overrides,
  };
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TemplateChecklistPanel template={TEMPLATE} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listTemplateTasks.mockResolvedValue([]);
});

describe('TemplateChecklistPanel', () => {
  it('says editing the checklist leaves existing projects alone', async () => {
    renderPanel();

    expect(
      await screen.findByText(/Existing projects keep the checklist they were registered with/i),
    ).toBeInTheDocument();
  });

  it('warns that an empty checklist means a project starts with no next action', async () => {
    renderPanel();

    expect(await screen.findByText(/This template has no checklist/i)).toBeInTheDocument();
    expect(screen.getByText(/its next action stays empty/i)).toBeInTheDocument();
  });

  it('states the offset in days rather than a bare number', async () => {
    listTemplateTasks.mockResolvedValue([
      item({ id: 'a', name: 'Confirm the finish', category: 'Spec-in', default_offset_days: 14 }),
    ]);

    renderPanel();

    expect(
      await screen.findByText(/Due 14 days after registration/i),
    ).toBeInTheDocument();
  });

  it('says so explicitly when an item has no default due date', async () => {
    listTemplateTasks.mockResolvedValue([
      item({ id: 'a', name: 'Whenever', default_offset_days: null }),
    ]);

    renderPanel();

    expect(await screen.findByText(/No default due date/i)).toBeInTheDocument();
  });

  it('offers deactivation instead of deletion once an item is in use', async () => {
    listTemplateTasks.mockResolvedValue([
      item({ id: 'a', name: 'Confirm the finish', in_use_count: 3 }),
    ]);
    updateTemplateTask.mockResolvedValue(item({ id: 'a', is_active: false }));

    renderPanel();

    fireEvent.click(await screen.findByLabelText('Delete Confirm the finish'));

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent(/already been copied into 3 project tasks/i);
    // No Delete button at all: offering one that the server is certain to refuse
    // teaches the user that the app is unreliable.
    expect(within(dialog).queryByRole('button', { name: /^Delete$/i })).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: /Deactivate/i }));

    await waitFor(() =>
      expect(updateTemplateTask).toHaveBeenCalledWith('tpl-1', 'a', { is_active: false }),
    );
    expect(deleteTemplateTask).not.toHaveBeenCalled();
  });

  it('does not offer to deactivate an item that is already inactive', async () => {
    listTemplateTasks.mockResolvedValue([
      item({ id: 'a', name: 'Confirm the finish', in_use_count: 3, is_active: false }),
    ]);

    renderPanel();

    fireEvent.click(await screen.findByLabelText('Delete Confirm the finish'));

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent(/already inactive/i);
    expect(within(dialog).queryByRole('button', { name: /Deactivate/i })).not.toBeInTheDocument();
  });

  it('allows deleting an item nothing has copied yet', async () => {
    listTemplateTasks.mockResolvedValue([item({ id: 'a', name: 'Brand new', in_use_count: 0 })]);
    deleteTemplateTask.mockResolvedValue(undefined);

    renderPanel();

    fireEvent.click(await screen.findByLabelText('Delete Brand new'));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent(/Projects already registered keep their copy/i);

    fireEvent.click(within(dialog).getByRole('button', { name: /^Delete$/i }));

    await waitFor(() => expect(deleteTemplateTask).toHaveBeenCalledWith('tpl-1', 'a'));
  });
});

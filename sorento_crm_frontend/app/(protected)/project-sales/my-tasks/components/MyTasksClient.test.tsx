/**
 * S2b - MyTasksClient (AC-N9).
 *
 * The worklist's job is to answer "what do I do now", so what is pinned here is the
 * bucketing and the fact that the request includes the owner's unassigned work by
 * default. Row cosmetics are not.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectTask } from '../../_shared/types/project.types';

const listMyTasks = vi.fn();

vi.mock('../../_shared/services/projectService', () => ({
  listMyTasks: (...args: unknown[]) => listMyTasks(...args),
  listProjectTasks: vi.fn(),
  createProjectTask: vi.fn(),
  updateProjectTask: vi.fn(),
  changeTaskStatus: vi.fn(),
  deleteProjectTask: vi.fn(),
  getTaskHistory: vi.fn(),
  listTemplateTasks: vi.fn(),
  createTemplateTask: vi.fn(),
  updateTemplateTask: vi.fn(),
  deleteTemplateTask: vi.fn(),
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

import { MyTasksClient } from './MyTasksClient';

function task(overrides: Partial<ProjectTask> = {}): ProjectTask {
  return {
    id: 't1',
    project_id: 'p1',
    project_code: 'PRJ-000001',
    project_title: 'Menara Test',
    name: 'Task',
    task_phase: 'pursuit',
    status_label: 'In Progress',
    is_open: true,
    is_overdue: false,
    sort_order: 0,
    can_edit: true,
    ...overrides,
  };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MyTasksClient />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listMyTasks.mockResolvedValue({ data: [], total: 0 });
});

describe('MyTasksClient', () => {
  it('includes unassigned work on my own projects by default', async () => {
    renderClient();

    await waitFor(() =>
      expect(listMyTasks).toHaveBeenCalledWith({
        include_unassigned_owned: true,
        limit: 200,
      }),
    );
  });

  it('drops the owner filter when the box is unticked', async () => {
    renderClient();
    await screen.findByText(/Nothing open against your name/i);

    fireEvent.click(screen.getByLabelText(/Include unassigned work on my projects/i));

    await waitFor(() =>
      expect(listMyTasks).toHaveBeenLastCalledWith({
        include_unassigned_owned: false,
        limit: 200,
      }),
    );
  });

  it('buckets by urgency and renders only the buckets that have work', async () => {
    listMyTasks.mockResolvedValue({
      data: [
        task({ id: 'a', name: 'Late', due_date: '2026-07-01', is_overdue: true }),
        task({ id: 'b', name: 'Today', due_date: '2026-07-26', days_until_due: 0 }),
        task({ id: 'c', name: 'Undated' }),
      ],
      total: 3,
    });

    renderClient();

    expect(await screen.findByText('Overdue')).toBeInTheDocument();
    expect(screen.getByText('Due today')).toBeInTheDocument();
    expect(screen.getByText('No due date')).toBeInTheDocument();
    // Nothing falls in these two, so no empty heading implies missing work.
    expect(screen.queryByText('Due this week')).not.toBeInTheDocument();
    expect(screen.queryByText('Later')).not.toBeInTheDocument();
  });

  it('links each row to the project by its code, never by an id', async () => {
    listMyTasks.mockResolvedValue({
      data: [task({ id: 'a', name: 'Chase the QS' })],
      total: 1,
    });

    renderClient();

    const link = await screen.findByRole('link', { name: /PRJ-000001/ });
    expect(link).toHaveAttribute('href', '/project-sales/p1?tab=tasks');
    expect(link.textContent).not.toMatch(/p1/);
  });

  it('explains how work arrives here when there is none', async () => {
    renderClient();

    expect(await screen.findByText(/Nothing open against your name/i)).toBeInTheDocument();
    expect(screen.getByText(/escalates one to you/i)).toBeInTheDocument();
  });

  it('reports a load failure instead of looking empty', async () => {
    listMyTasks.mockRejectedValue(new Error('Backend is down'));

    renderClient();

    expect(await screen.findByText('Backend is down')).toBeInTheDocument();
  });
});

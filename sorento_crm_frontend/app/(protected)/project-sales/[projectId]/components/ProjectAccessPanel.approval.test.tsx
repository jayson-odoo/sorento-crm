/**
 * PROJECT-REG-PORTAL (security N3, final review round): nobody asks to join or disputes a
 * portal registration that is not a project yet, so the Access card offers neither button on a
 * pending or rejected one. The server answers 409 `project_not_approved` for the same request.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';

vi.mock('../../_shared/hooks/useProjects', () => ({
  useCollaborators: () => ({ data: [], isLoading: false }),
  useTakeoverRequests: () => ({ data: [] }),
  useTakeoverMutations: () => ({
    decide: { mutate: vi.fn(), isPending: false },
    request: { mutateAsync: vi.fn(), isPending: false },
  }),
}));

import { ProjectAccessPanel } from './ProjectAccessPanel';

function project(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000142',
    title: 'Someone Elses Tower',
    outcome: 'open',
    owner_name: 'Ali',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: false,
    approval_state: null,
    ...over,
  } as Project;
}

describe('ProjectAccessPanel: join and dispute', () => {
  it('a staff project someone else owns offers Ask to join and Dispute (the control)', () => {
    render(<ProjectAccessPanel project={project()} />);
    expect(screen.getByRole('button', { name: 'Ask to join' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dispute' })).toBeInTheDocument();
  });

  it.each(['pending', 'rejected'] as const)('a %s registration offers neither', (state) => {
    render(<ProjectAccessPanel project={project({ approval_state: state, project_code: null })} />);
    expect(screen.queryByRole('button', { name: 'Ask to join' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Dispute' })).toBeNull();
  });

  it('an approved registration offers them again', () => {
    render(<ProjectAccessPanel project={project({ approval_state: 'approved', project_code: 'PPF2610001' })} />);
    expect(screen.getByRole('button', { name: 'Ask to join' })).toBeInTheDocument();
  });
});

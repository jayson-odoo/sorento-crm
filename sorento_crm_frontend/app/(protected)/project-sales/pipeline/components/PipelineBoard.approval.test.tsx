/**
 * RW12 - the board shows registrations that wait for a decision (PLAN R6).
 *
 * A portal registration is a project with no code and no stage. It is not hidden and it is not
 * "a project with no stage" either: the board gets two lanes BEFORE the funnel stages,
 * "Awaiting approval" and "Rejected", fed by `approval_state`. Cards there show
 * "Awaiting approval" where the code would be, and nothing moves in or out of the two lanes
 * (Approve gives a project its first stage, never a drag).
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { PipelineBoard } from './PipelineBoard';
import type { Project } from '../../_shared/types/project.types';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function status(overrides: Record<string, unknown> = {}) {
  return {
    id: 's1',
    entity_type: 'project',
    scope_id: null,
    key: 'registered',
    label: 'Registered',
    description: null,
    color: null,
    icon: null,
    category: null,
    sort_order: 0,
    is_initial: true,
    is_terminal: false,
    is_active: true,
    is_archived: false,
    is_default: true,
    is_system: false,
    ...overrides,
  } as never;
}

const STATUSES = [
  status(),
  status({ id: 's2', key: 'quoted', label: 'Quoted', sort_order: 1, is_initial: false }),
];

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PPF2610001',
    title: 'Setia Alam Phase 3B',
    outcome: 'open',
    status_id: 's1',
    status_key: 'registered',
    status_label: 'Registered',
    approval_state: null,
    developer_name: null,
    owner_name: 'Ali',
    is_critical: false,
    brands: [],
    brand_ids: [],
    can_edit: true,
    ...overrides,
  } as Project;
}

const PENDING = (over: Partial<Project> = {}) =>
  project({
    id: 'p-pend',
    project_code: null,
    title: 'Pending Tower',
    status_id: null,
    status_key: null,
    status_label: null,
    approval_state: 'pending',
    ...over,
  });
const REJECTED = (over: Partial<Project> = {}) =>
  project({
    id: 'p-rej',
    project_code: null,
    title: 'Rejected Tower',
    status_id: null,
    status_key: null,
    status_label: null,
    approval_state: 'rejected',
    ...over,
  });

function lane(name: string): HTMLElement {
  const heading = screen.getByRole('heading', { name, level: 3 });
  return heading.closest('section') as HTMLElement;
}

function card(title: string): HTMLElement {
  return screen.getByText(title).closest('li') as HTMLElement;
}

describe('PipelineBoard: Awaiting approval and Rejected lanes (RW12)', () => {
  it('puts the two lanes before the funnel stages, in that order', () => {
    render(<PipelineBoard statuses={STATUSES} projects={[PENDING(), REJECTED(), project()]} onMove={vi.fn()} />);
    const names = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent?.trim());
    expect(names).toEqual(['Awaiting approval', 'Rejected', 'Registered', 'Quoted']);
  });

  it('counts each lane by its own cards', () => {
    render(
      <PipelineBoard
        statuses={STATUSES}
        projects={[PENDING(), PENDING({ id: 'p-pend2', title: 'Pending Tower Two' }), REJECTED(), project()]}
        onMove={vi.fn()}
      />,
    );
    const header = (name: string) => screen.getByRole('heading', { name, level: 3 }).parentElement as HTMLElement;
    expect(within(header('Awaiting approval')).getByText('2')).toBeInTheDocument();
    expect(within(header('Rejected')).getByText('1')).toBeInTheDocument();
    expect(within(header('Registered')).getByText('1')).toBeInTheDocument();
    expect(within(lane('Awaiting approval')).getAllByRole('listitem')).toHaveLength(2);
    expect(within(lane('Rejected')).getAllByRole('listitem')).toHaveLength(1);
    expect(within(lane('Registered')).getAllByRole('listitem')).toHaveLength(1);
  });

  it('files each card in its own lane by approval_state', () => {
    render(<PipelineBoard statuses={STATUSES} projects={[PENDING(), REJECTED(), project()]} onMove={vi.fn()} />);
    expect(within(lane('Awaiting approval')).getByText('Pending Tower')).toBeInTheDocument();
    expect(within(lane('Awaiting approval')).queryByText('Rejected Tower')).toBeNull();
    expect(within(lane('Rejected')).getByText('Rejected Tower')).toBeInTheDocument();
    expect(within(lane('Registered')).getByText('Setia Alam Phase 3B')).toBeInTheDocument();
  });

  it('is not the "no stage" warning: a pending project has no stage by design', () => {
    render(<PipelineBoard statuses={STATUSES} projects={[PENDING(), REJECTED()]} onMove={vi.fn()} />);
    expect(screen.queryByText(/with no stage/i)).toBeNull();
  });

  it('a card shows "Awaiting approval" where the code would be, never None or null', () => {
    render(<PipelineBoard statuses={STATUSES} projects={[PENDING(), REJECTED(), project()]} onMove={vi.fn()} />);
    expect(within(card('Pending Tower')).getByText('Awaiting approval')).toBeInTheDocument();
    // Review round 3: a rejected registration's code slot says Rejected.
    expect(within(card('Rejected Tower')).getByText('Rejected')).toBeInTheDocument();
    expect(within(card('Rejected Tower')).queryByText('Awaiting approval')).toBeNull();
    expect(within(card('Setia Alam Phase 3B')).getByText('PPF2610001')).toBeInTheDocument();
    expect(within(card('Setia Alam Phase 3B')).queryByText('Awaiting approval')).toBeNull();
    expect(screen.queryByText(/\b(none|null|undefined)\b/i)).toBeNull();
    expect(card('Pending Tower').textContent).not.toMatch(/none|null|undefined/i);
  });

  it('a card links to its project', () => {
    render(<PipelineBoard statuses={STATUSES} projects={[PENDING()]} onMove={vi.fn()} />);
    expect(screen.getByRole('link', { name: /Pending Tower/ })).toHaveAttribute('href', '/project-sales/p-pend');
  });

  it('shows both lanes with a count of 0 when nothing waits', () => {
    render(<PipelineBoard statuses={STATUSES} projects={[project()]} onMove={vi.fn()} />);
    for (const name of ['Awaiting approval', 'Rejected']) {
      const header = screen.getByRole('heading', { name, level: 3 }).parentElement as HTMLElement;
      expect(within(header).getByText('0')).toBeInTheDocument();
    }
  });
});

describe('PipelineBoard: nothing moves in or out of the two lanes (RW12)', () => {
  it('a pending or rejected card is not draggable, even when the user can edit it', () => {
    const { container } = render(
      <PipelineBoard
        statuses={STATUSES}
        projects={[PENDING({ can_edit: true }), REJECTED({ can_edit: true }), project()]}
        onMove={vi.fn()}
      />,
    );
    expect(container.querySelectorAll('li[draggable="true"]')).toHaveLength(1);
    expect(card('Pending Tower')).toHaveAttribute('draggable', 'false');
    expect(card('Rejected Tower')).toHaveAttribute('draggable', 'false');
  });

  it('dropping a staged card on a waiting lane never asks the server to move it', () => {
    const onMove = vi.fn();
    render(<PipelineBoard statuses={STATUSES} projects={[PENDING(), REJECTED(), project()]} onMove={onMove} />);
    for (const name of ['Awaiting approval', 'Rejected']) {
      fireEvent.drop(lane(name), { dataTransfer: { getData: () => 'p1' } });
    }
    expect(onMove).not.toHaveBeenCalled();
  });

  it('dropping a pending or rejected card on a stage never asks the server to move it', () => {
    const onMove = vi.fn();
    render(<PipelineBoard statuses={STATUSES} projects={[PENDING(), REJECTED(), project()]} onMove={onMove} />);
    fireEvent.drop(lane('Quoted'), { dataTransfer: { getData: () => 'p-pend' } });
    fireEvent.drop(lane('Quoted'), { dataTransfer: { getData: () => 'p-rej' } });
    expect(onMove).not.toHaveBeenCalled();
  });

  it('an ordinary move between two stages still works', () => {
    const onMove = vi.fn();
    render(<PipelineBoard statuses={STATUSES} projects={[PENDING(), project()]} onMove={onMove} />);
    fireEvent.drop(lane('Quoted'), { dataTransfer: { getData: () => 'p1' } });
    expect(onMove).toHaveBeenCalledWith('p1', 's2');
  });
});

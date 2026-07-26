/**
 * S2 — PipelineBoard (AC-G3, AC-G4).
 *
 * Two things here are invisible to the eye and easy to regress: which cards are
 * draggable (only ones the server would let you edit) and where a project with no
 * status ends up (visible and fixable, not silently dropped from the board).
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
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
    key: 'identified',
    label: 'Identified',
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

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Setia Alam Phase 3B',
    outcome: 'open',
    status_id: 's1',
    status_key: 'identified',
    status_label: 'Identified',
    developer_name: 'SP Setia',
    owner_name: 'Ali',
    is_critical: false,
    brands: [],
    brand_ids: [],
    can_edit: true,
    ...overrides,
  } as Project;
}

describe('PipelineBoard', () => {
  it('points at the status admin when no stages are configured', () => {
    render(<PipelineBoard statuses={[]} projects={[]} onMove={vi.fn()} />);
    expect(screen.getByText(/No pipeline stages configured/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Configure stages/i })).toHaveAttribute(
      'href',
      '/system-management/status-graphs',
    );
  });

  it('distinguishes an empty live column from an empty terminal one', () => {
    // "Drop a project here" under Lost would be an invitation to do the wrong thing.
    render(
      <PipelineBoard
        statuses={[status(), status({ id: 's2', key: 'lost', label: 'Lost', is_terminal: true })]}
        projects={[]}
        onMove={vi.fn()}
      />,
    );
    expect(screen.getByText('Drop a project here')).toBeInTheDocument();
    expect(screen.getByText('Nothing closed here yet')).toBeInTheDocument();
  });

  it('only makes cards draggable when the user can actually edit them', () => {
    // A card that moves and then snaps back with a 403 is worse than one that never
    // moved, so the affordance mirrors the server's answer rather than guessing.
    const { container } = render(
      <PipelineBoard
        statuses={[status()]}
        projects={[project(), project({ id: 'p2', project_code: 'PRJ-000002', can_edit: false })]}
        onMove={vi.fn()}
      />,
    );
    // draggable="false" still renders the attribute, so match on the value.
    const draggable = container.querySelectorAll('li[draggable="true"]');
    expect(draggable).toHaveLength(1);
    expect(within(draggable[0] as HTMLElement).getByText('PRJ-000001')).toBeInTheDocument();
    expect(container.querySelectorAll('li[draggable="false"]')).toHaveLength(1);
  });

  it('surfaces projects with no stage instead of dropping them off the board', () => {
    render(
      <PipelineBoard
        statuses={[status()]}
        projects={[project({ status_id: null, status_label: null })]}
        onMove={vi.fn()}
      />,
    );
    expect(screen.getByText(/1 project with no stage/i)).toBeInTheDocument();
    expect(screen.getByText('PRJ-000001')).toBeInTheDocument();
  });

  it('badges the signals a salesperson scans for (AC-G4)', () => {
    render(
      <PipelineBoard
        statuses={[status()]}
        projects={[
          project({
            is_critical: true,
            days_since_last_activity: 45,
            estimated_sales_value: '1250000.00',
            brands: ['Sorento', 'Mocha', 'Third'],
          }),
        ]}
        onMove={vi.fn()}
      />,
    );
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('45d quiet')).toBeInTheDocument();
    expect(screen.getByText('RM 1.3m')).toBeInTheDocument();
    // Only the first two brands, then a count -- a card is a glance, not a list.
    expect(screen.getByText('+1')).toBeInTheDocument();
  });

  it('does not call a recently-touched project stale', () => {
    render(
      <PipelineBoard
        statuses={[status()]}
        projects={[project({ days_since_last_activity: 3 })]}
        onMove={vi.fn()}
      />,
    );
    expect(screen.queryByText(/quiet/i)).not.toBeInTheDocument();
  });

  it('counts the cards in each column', () => {
    render(
      <PipelineBoard
        statuses={[status(), status({ id: 's2', key: 'quoted', label: 'Quoted' })]}
        projects={[project(), project({ id: 'p2', project_code: 'PRJ-000002' })]}
        onMove={vi.fn()}
      />,
    );
    const identified = screen.getByRole('heading', { name: 'Identified' }).closest('section');
    expect(within(identified as HTMLElement).getByText('2')).toBeInTheDocument();
  });
});

/**
 * PROJECT-REGISTER-V2 G3: board cards carry no brand badges (and no "+N" overflow badge).
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PipelineBoard } from './PipelineBoard';
import type { Project } from '../../_shared/types/project.types';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const STATUS = {
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
} as never;

describe('G3 PipelineBoard shows no brand badges', () => {
  it('prints none of a card\'s brands and no +N overflow', () => {
    const p = {
      id: 'p1',
      project_code: 'PPF2610001',
      title: 'Setia Alam Phase 3B CONTOH',
      outcome: 'open',
      status_id: 's1',
      status_key: 'registered',
      status_label: 'Registered',
      approval_state: null,
      owner_name: 'Sales A',
      is_critical: false,
      brands: ['Brand One CONTOH', 'Brand Two CONTOH', 'Brand Three CONTOH'],
      brand_ids: ['b1', 'b2', 'b3'],
      can_edit: true,
    } as unknown as Project;
    render(<PipelineBoard statuses={[STATUS]} projects={[p]} onMove={vi.fn()} />);
    expect(screen.getByText('Setia Alam Phase 3B CONTOH')).toBeInTheDocument();
    expect(screen.queryAllByText(/Brand (One|Two|Three) CONTOH/)).toHaveLength(0);
    expect(screen.queryByText('+1')).toBeNull();
  });
});

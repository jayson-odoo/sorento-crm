/**
 * PROJECT-REGISTER-V2 G3 (no brand badges) and D2 / D3 (one line per candidate) on the clash
 * panel. The panel is given candidates only; the Register interest button is the form's primary,
 * not a row button (covered in ProjectForm.v2.test.tsx).
 */
import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { ClashWarningPanel } from './ClashWarningPanel';
import type { ClashCandidate } from '../../_shared/types/project.types';


function candidate(over: Partial<ClashCandidate> = {}): ClashCandidate {
  return {
    project_id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Setia Alam Phase 3B CONTOH',
    outcome: 'open',
    status_label: 'Registered',
    owner_user_id: 'u1',
    owner_name: 'Manager M',
    developer_name: 'SP Setia CONTOH',
    estimated_sales_value: '850000.00',
    last_activity_at: null,
    brands: [],
    similarity: 0.86,
    blocks: true,
    ...over,
  } as ClashCandidate;
}

function lines(text: string): HTMLElement[] {
  const norm = (s: string | null) => (s ?? '').replace(/\s+/g, ' ').trim();
  const all = Array.from(document.body.querySelectorAll<HTMLElement>('*')).filter(
    (el) => norm(el.textContent) === text,
  );
  return all.filter((el) => !Array.from(el.children).some((c) => all.includes(c as HTMLElement)));
}

describe('G3 the clash panel shows no brand badges', () => {
  it('prints no brand names for the incumbent', () => {
    render(<ClashWarningPanel candidates={[candidate({ brands: ['Sorento CONTOH'] } as Partial<ClashCandidate>)]} />);
    expect(screen.queryByText('Sorento CONTOH')).toBeNull();
  });
});

describe('D2 / D3 one line per candidate', () => {
  it('a blocking candidate is ONE line "Project already registered: <code> <title>" with no owner, stage or similarity', () => {
    render(<ClashWarningPanel candidates={[candidate()]} />);
    const found = lines('Project already registered: PRJ-000001 Setia Alam Phase 3B CONTOH');
    expect(found).toHaveLength(1);
    expect(within(found[0]).queryByRole('button')).toBeNull();
    expect(screen.queryByText('Manager M')).toBeNull();
    expect(screen.queryByText('Registered')).toBeNull();
    expect(screen.queryByText(/RM 850,000/)).toBeNull();
    expect(screen.queryByText(/Already registered to someone else/i)).toBeNull();
  });

  it('a non-blocking candidate is ONE line "Similar project: <code> <title>" with no action', () => {
    render(<ClashWarningPanel candidates={[candidate({ blocks: false })]} />);
    const found = lines('Similar project: PRJ-000001 Setia Alam Phase 3B CONTOH');
    expect(found).toHaveLength(1);
    expect(within(found[0]).queryByRole('button')).toBeNull();
  });

  it('never prints the word Dispute, even when a handler is passed', () => {
    render(<ClashWarningPanel candidates={[candidate()]} onDispute={() => {}} onRequestJoin={() => {}} />);
    expect(screen.queryByText(/Dispute/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Ask to join|Register interest/ })).toBeNull();
  });
});

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

  it('never prints the word Dispute or any row button', () => {
    render(<ClashWarningPanel candidates={[candidate()]} />);
    expect(screen.queryByText(/Dispute/)).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('below sm the title drops to its own truncated line; label and code keep their size', () => {
  const TITLE = 'Setia Alam Phase 3B CONTOH';
  it.each([
    ['blocking', 'Project already registered:', true],
    ['similar', 'Similar project:', false],
  ])('%s line structure', (_n, label, blocks) => {
    render(<ClashWarningPanel candidates={[candidate({ blocks })]} />);
    const labelEl = screen.getByText(label);
    const row = labelEl.parentElement as HTMLElement;
    const code = within(row).getByRole('link', { name: 'PRJ-000001' });
    const title = within(row).getByTitle(TITLE);

    expect(row.className).toMatch(/\bflex\b/);
    expect(row.className).toMatch(/\bflex-wrap\b/);
    expect(row.className).not.toMatch(/\[flex-flow/);
    expect(row.className).toMatch(/\bmin-w-0\b/);
    expect(labelEl.className).toMatch(/\bshrink-0\b/);
    expect(code.className).toMatch(/\bshrink-0\b/);
    expect(title).not.toBe(code);
    expect(title.className).toMatch(/\btruncate\b/);
    expect(title.className).toMatch(/\bmin-w-0\b/);
    expect(title.className).toMatch(/(^|\s)basis-full\b/);
    expect(title.className).toMatch(/\bsm:basis-auto\b/);
    expect(title).toHaveAttribute('title', TITLE);
  });
});

describe('a masked candidate (salesperson Check)', () => {
  it('has no outcome field and renders no badge or pill on its line', () => {
    const masked = {
      project_id: 'p9',
      project_code: 'PRJ-000009',
      title: 'Setia Alam Phase 3B CONTOH',
      blocks: true,
    } as unknown as ClashCandidate;
    const { container } = render(<ClashWarningPanel candidates={[masked]} />);
    expect(screen.getByText('PRJ-000009')).toBeInTheDocument();
    expect(container.querySelector('[data-slot="badge"]')).toBeNull();
  });
});

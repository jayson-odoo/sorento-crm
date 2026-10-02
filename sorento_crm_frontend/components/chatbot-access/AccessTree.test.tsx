/**
 * Access model S6 (AC-AM-2, AC-AM-4b, AC-AM-7, AC-AM-17). Red test: AccessTree.tsx does not exist.
 * Props: sections (shape from lib/chatbot-access/tree.ts buildTree), editable, onToggle(key).
 * A row may carry handoff: { tier1, agent, team } for the "Hand-off: <tier1> ..." line.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import AccessTree from './AccessTree';

afterEach(cleanup);

const kid = (key: string, label: string, checked: boolean, source: 'role' | 'added' | 'removed' | null, roleNames: string[] = []) => ({
  key, label, checked, source, roleNames,
});

const sections = [
  {
    key: 'domains',
    label: 'Domains',
    rows: [
      {
        key: 'inventory', label: 'Stock', kind: 'domain', checked: true, indeterminate: false, blocked: false,
        source: 'role', roleNames: ['Purchasing'],
        handoff: { tier1: 'Warehouse Executive', agent: 'General Enquiries', team: 'warehouse' },
        children: [],
      },
      {
        key: 'incoming', label: 'Incoming stock', kind: 'domain', checked: true, indeterminate: true, blocked: false,
        source: 'role', roleNames: ['Purchasing'],
        handoff: { tier1: 'Purchasing - Incoming', agent: 'Incoming Stock Enquiries', team: 'purchasing' },
        children: [
          kid('incoming.eta', 'ETA', true, 'role', ['Purchasing']),
          kid('incoming.consignee', 'Consignee', true, 'added'),
          kid('incoming.liner', 'Liner code', false, 'removed'),
        ],
      },
      { key: 'order', label: 'Orders / DO', kind: 'domain', checked: false, indeterminate: false, blocked: false, source: null, roleNames: [], children: [] },
    ],
  },
  {
    key: 'reports',
    label: 'Reports',
    rows: [
      { key: 'low_stock', label: 'Low stock report', kind: 'report', checked: true, indeterminate: false, blocked: true, needs: 'Stock', source: 'role', roleNames: ['Warehouse'], children: [] },
    ],
  },
];

describe('AccessTree', () => {
  it('AC-AM-4b renders the Domains and Reports headings and row labels', () => {
    render(<AccessTree sections={sections as never} editable onToggle={vi.fn()} />);
    expect(screen.getByText('Domains')).toBeTruthy();
    expect(screen.getByText('Reports')).toBeTruthy();
    expect(screen.getByText('Stock')).toBeTruthy();
    expect(screen.getByText('Low stock report')).toBeTruthy();
  });

  it('AC-AM-7 shows from <role>, added here and removed here badges', () => {
    render(<AccessTree sections={sections as never} editable onToggle={vi.fn()} />);
    expect(screen.getAllByText('from Purchasing').length).toBeGreaterThan(0);
    expect(screen.getByText('added here')).toBeTruthy();
    expect(screen.getByText('removed here')).toBeTruthy();
  });

  it('AC-AM-4b a blocked report shows "Needs Stock"', () => {
    render(<AccessTree sections={sections as never} editable onToggle={vi.fn()} />);
    expect(screen.getByText('Needs Stock')).toBeTruthy();
  });

  it('AC-AM-17 shows the hand-off line with the tier-1 team when provided', () => {
    render(<AccessTree sections={sections as never} editable onToggle={vi.fn()} />);
    expect(screen.getByText(/Hand-off: Warehouse Executive/)).toBeTruthy();
    expect(screen.getByText(/Hand-off: Purchasing - Incoming/)).toBeTruthy();
  });

  it('AC-AM-2 an indeterminate domain checkbox has aria-checked="mixed"', () => {
    render(<AccessTree sections={sections as never} editable onToggle={vi.fn()} />);
    expect(screen.getByRole('checkbox', { name: 'Incoming stock' }).getAttribute('aria-checked')).toBe('mixed');
    expect(screen.getByRole('checkbox', { name: 'Stock' }).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByRole('checkbox', { name: 'Orders / DO' }).getAttribute('aria-checked')).toBe('false');
  });

  it('AC-AM-2 clicking a domain and a nested field calls onToggle with the key', () => {
    const onToggle = vi.fn();
    render(<AccessTree sections={sections as never} editable onToggle={onToggle} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Orders / DO' }));
    expect(onToggle.mock.calls.at(-1)![0]).toBe('order');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Consignee' }));
    expect(onToggle.mock.calls.at(-1)![0]).toBe('incoming.consignee');
  });

  it('AC-AM-2 read-only mode disables the checkboxes and never calls onToggle', () => {
    const onToggle = vi.fn();
    render(<AccessTree sections={sections as never} editable={false} onToggle={onToggle} />);
    const box = screen.getByRole('checkbox', { name: 'Orders / DO' }) as HTMLButtonElement;
    expect(box.disabled || box.getAttribute('aria-disabled') === 'true').toBe(true);
    fireEvent.click(box);
    expect(onToggle).not.toHaveBeenCalled();
  });
});

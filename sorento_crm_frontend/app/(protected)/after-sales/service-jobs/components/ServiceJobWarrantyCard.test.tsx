/**
 * AFTER-SALES-P2 red tests (UAC F1, E): the Warranty card on the job page, Details tab.
 *
 * Module the coder builds: `./ServiceJobWarrantyCard` default export, props `{ warranty: WarrantyLine[] }`
 * where the array is the job's `warranty` field (backend wire):
 *   WarrantyLine = { id, product_code, product_name, kind_name, purchase_date, defect_label,
 *                    verdicts: { part_name: string|null, verdict: 'covered'|'expired'|'defect_not_covered'|'no_term'|'unknown',
 *                                expiry: 'YYYY-MM-DD'|null, reason: string, is_lifetime, installation_included, policy_version }[] }
 * One table row per verdict. Columns Product, Part, Answer (pill), Until, Reason. Pure props, no hooks.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import ServiceJobWarrantyCard from './ServiceJobWarrantyCard';

const verdict = (over: Record<string, unknown>) => ({
  part_name: 'Ceramic Body', verdict: 'covered', expiry: '2030-03-15', reason: 'Covered for 10 years from 15/03/2020',
  is_lifetime: false, installation_included: false, policy_version: 'v15', ...over,
});
const line = (over: Record<string, unknown>) => ({
  id: 'w-1', product_code: 'DEMO-WC-02', product_name: 'Demo one piece water closet', kind_name: 'Water Closet',
  purchase_date: '2020-03-15', defect_label: 'Leakage', verdicts: [verdict({})], ...over,
});

const pillOf = (text: string) => screen.getByText(text).closest('[data-slot="badge"]');

describe('ServiceJobWarrantyCard', () => {
  it('has the title and the five columns', () => {
    render(<ServiceJobWarrantyCard warranty={[line({}) as never]} />);
    expect(screen.getByText('Warranty')).toBeInTheDocument();
    const heads = screen.getAllByRole('columnheader').map((h) => (h.textContent || '').trim()).filter(Boolean);
    expect(heads).toEqual(['Product', 'Part', 'Answer', 'Until', 'Reason']);
  });

  it('a covered term shows the pill, Until as dd/mm/yyyy and the reason', () => {
    render(<ServiceJobWarrantyCard warranty={[line({}) as never]} />);
    const row = screen.getByText('Ceramic Body').closest('tr')!;
    expect(within(row).getByText('DEMO-WC-02', { exact: false })).toBeInTheDocument();
    expect(pillOf('Covered')).not.toBeNull();
    expect(within(row).getByText('15/03/2030')).toBeInTheDocument();
    expect(within(row).getByText('Covered for 10 years from 15/03/2020')).toBeInTheDocument();
  });

  it.each([
    ['expired', 'Expired'],
    ['defect_not_covered', 'Defect not covered'],
    ['no_term', 'No term'],
    ['unknown', 'Unknown'],
  ])('labels the %s answer "%s" in a pill', (code, label) => {
    render(<ServiceJobWarrantyCard warranty={[line({ verdicts: [verdict({ verdict: code, expiry: null })] }) as never]} />);
    expect(pillOf(label)).not.toBeNull();
  });

  it('a line with no kind shows the exact reason and a dash for Until', () => {
    const w = line({
      kind_name: null,
      verdicts: [verdict({ part_name: null, verdict: 'unknown', expiry: null, reason: 'No warranty rule for this product yet' })],
    });
    render(<ServiceJobWarrantyCard warranty={[w as never]} />);
    const row = screen.getByText('No warranty rule for this product yet').closest('tr')!;
    expect(within(row).getAllByText('-').length).toBeGreaterThanOrEqual(2); // Part and Until
  });

  it('one row per product and term', () => {
    const w = line({ verdicts: [verdict({}), verdict({ part_name: 'Flushing Fittings', expiry: '2025-03-15', verdict: 'expired' })] });
    render(<ServiceJobWarrantyCard warranty={[w as never]} />);
    expect(screen.getByText('Ceramic Body').closest('tr')).not.toBe(screen.getByText('Flushing Fittings').closest('tr'));
  });

  it('empty state is a heading and a hint with no button', () => {
    render(<ServiceJobWarrantyCard warranty={[]} />);
    const heading = screen.getByRole('heading', { name: /no warranty/i });
    expect(within(heading.parentElement as HTMLElement).queryByRole('button')).toBeNull();
    expect((heading.parentElement as HTMLElement).textContent!.length).toBeGreaterThan(heading.textContent!.length);
  });

  it('renders no UUID', () => {
    const { container } = render(<ServiceJobWarrantyCard warranty={[line({ id: '3f2b8c1e-aaaa-4bbb-8ccc-123456789abc' }) as never]} />);
    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });
});

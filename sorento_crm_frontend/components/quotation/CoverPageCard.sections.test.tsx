/**
 * QUOTE-COVER-FIELDS: a layout 4 cover draws its sections (band label, columns, the section
 * style) in the card the sign link, the Cover letter tab and the designer preview share.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { CoverPageData } from '@/lib/quotation-cover';
import { CoverPageCard } from './CoverPageCard';

const cover: CoverPageData = {
  sender_name: 'Sample Co',
  sender_logo_url: null,
  cover_title: 'QUOTATION',
  cover_show_letterhead: true,
  cover_rows: [{ key: 'to_name', label: 'Company', text: 'SAMPLE BUILDERS' }],
  cover_sections: [
    {
      style: 'fields',
      label: 'Propose to:',
      columns: 2,
      cells: [
        [{ source: 'to_name', label: 'Company', text: 'SAMPLE BUILDERS' }],
        [{ source: 'document_no', label: 'Reference No', text: 'PRJQ-1-A' }],
      ],
    },
    {
      style: 'numbered',
      label: 'Term & Condition:',
      columns: 2,
      cells: [
        [{ source: 'terms', label: 'Price basis', html: '<p>Prices in RM</p>' }],
        [{ source: 'payment_terms', label: 'Terms of payment', text: '30 days' }],
      ],
    },
    {
      style: 'signature',
      label: 'Prepared by,',
      columns: 1,
      cells: [[{ source: 'prepared_by_name', label: 'Name', text: 'Person D' }]],
    },
    {
      style: 'footer',
      label: '',
      columns: 1,
      cells: [[{ source: 'company_fax', label: 'Fax', text: '03-0000 0003' }]],
    },
  ],
};

describe('CoverPageCard sections (layout 4)', () => {
  it('draws each section with its label, its columns and its style, and not the flat rows', () => {
    render(<CoverPageCard cover={cover} wide />);
    const sections = within(screen.getByTestId('cover-sections')).getAllByRole('region');
    expect(sections.map((s) => s.getAttribute('data-style'))).toEqual([
      'fields',
      'numbered',
      'signature',
    ]);
    const propose = screen.getByRole('region', { name: 'Propose to:' });
    expect(within(propose).getByText('SAMPLE BUILDERS')).toBeInTheDocument();
    expect(within(propose).getByText('PRJQ-1-A')).toBeInTheDocument();
    expect(
      (propose.querySelector('.grid') as HTMLElement).style.getPropertyValue('--cover-cols'),
    ).toBe('2');
  });

  it('numbers a numbered section on across its columns and prints the terms html', () => {
    render(<CoverPageCard cover={cover} wide />);
    const terms = screen.getByRole('region', { name: 'Term & Condition:' });
    const lists = terms.querySelectorAll('ol');
    expect(Array.from(lists).map((list) => list.getAttribute('start'))).toEqual(['1', '2']);
    expect(within(terms).getByText('Prices in RM')).toBeInTheDocument();
  });

  it('prints the footer with its label and the signature block', () => {
    render(<CoverPageCard cover={cover} wide />);
    expect(screen.getByText('Fax: 03-0000 0003')).toBeInTheDocument();
    expect(screen.getByText('Prepared by,')).toBeInTheDocument();
    expect(screen.getByText('Person D')).toBeInTheDocument();
  });
});

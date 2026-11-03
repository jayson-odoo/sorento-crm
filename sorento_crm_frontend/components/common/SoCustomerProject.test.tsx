/**
 * OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 19:35): wherever a sales order is named, its customer and
 * project are named beside it, in ONE format: `CUSTOMER / project` (the SO list's own two
 * fields, `customer_name` and `project_label`). A missing half is left out, never an id.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SoCustomerProject, soCustomerProjectLabel } from './SoCustomerProject';

describe('soCustomerProjectLabel', () => {
  it('joins customer and project with " / "', () => {
    expect(soCustomerProjectLabel('ACME SDN BHD (PROJECT)', 'TAMAN JAYA')).toBe(
      'ACME SDN BHD (PROJECT) / TAMAN JAYA',
    );
  });
  it('keeps the half that exists', () => {
    expect(soCustomerProjectLabel('ACME SDN BHD', null)).toBe('ACME SDN BHD');
    expect(soCustomerProjectLabel(undefined, 'TAMAN JAYA')).toBe('TAMAN JAYA');
  });
  it('trims, and treats blank as missing', () => {
    expect(soCustomerProjectLabel('  ACME  ', '   ')).toBe('ACME');
  });
  it('is null when neither is known', () => {
    expect(soCustomerProjectLabel(null, '')).toBeNull();
  });
});

describe('<SoCustomerProject>', () => {
  it('prints the label with the full text as its title (it truncates)', () => {
    render(<SoCustomerProject customer="ACME SDN BHD" project="TAMAN JAYA" />);
    const el = screen.getByText('ACME SDN BHD / TAMAN JAYA');
    expect(el).toHaveAttribute('title', 'ACME SDN BHD / TAMAN JAYA');
    expect(el.className).toMatch(/truncate/);
  });
  it('renders nothing when neither half is known', () => {
    const { container } = render(<SoCustomerProject customer={null} project={null} />);
    expect(container).toBeEmptyDOMElement();
  });
  it('can state the empty case in words when asked', () => {
    render(<SoCustomerProject customer={null} project={null} emptyText="-" />);
    expect(screen.getByText('-')).toBeInTheDocument();
  });
});

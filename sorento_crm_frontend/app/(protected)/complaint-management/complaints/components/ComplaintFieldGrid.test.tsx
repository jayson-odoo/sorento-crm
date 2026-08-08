/**
 * A retail complaint must not open as a page of dashes.
 *
 * Before the split, one screen rendered both field sets, so a complaint lodged from the
 * consumer portal showed Delivery Order Number, Customer Type, Salesperson and Project
 * Title with a dash beside each - and a dash could not be read: "blank because this is
 * retail" looked exactly like "blank because nobody filled it in". The Site address and
 * the pin, which are the only two things that get a technician to the right house, were
 * not shown at all.
 *
 * These tests assert the absence of the project fields as hard as the presence of the
 * retail ones. Absence is the whole point of the change, and a grid that quietly started
 * rendering them again would otherwise still pass.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ComplaintFieldGrid } from './ComplaintFieldGrid';
import type { Complaint } from '../types/complaint.types';

function complaint(overrides: Partial<Complaint> = {}): Complaint {
  return {
    id: 'c1',
    attachments: [],
    ...overrides,
  } as Complaint;
}

const RETAIL = complaint({
  reported_by_role: 'end_user',
  customer_name: 'Tester',
  contact_number: '+60123456789',
  site_address: '5 Jalan Impiana 1A, Taman Bukit Impiana, 43000 Kajang, Selangor, Malaysia',
  site_address_line1: '5 Jalan Impiana 1A',
  site_address_line2: 'Taman Bukit Impiana',
  site_postcode: '43000',
  site_city: 'Kajang',
  site_state: 'Selangor',
  site_country: 'Malaysia',
  latitude: '3.1184313',
  longitude: '101.6020993',
  defect_description: 'Cistern leaking from the base.',
  product_lines: [
    {
      product_code: 'SRTWC8152',
      claimed_text: 'the toilet in the guest bathroom',
      fault_description: 'Leaking since last week.',
      kind_name: 'Water Closet',
      quantity: '1',
    },
  ],
});

const PROJECT = complaint({
  delivery_order_number: 'DO-1',
  customer_type: 'Project',
  salesperson: 'Ahmad',
  project_title: 'Tower B refit',
  customer_address: 'Site office, Tower B',
  product_lines: [{ product_code: 'SRTWC8152', product_type: 'Sanitary', quantity: '4' }],
});

describe('a retail complaint', () => {
  it('shows who reported it', () => {
    render(<ComplaintFieldGrid complaint={RETAIL} />);
    expect(screen.getByText('Reported by')).toBeInTheDocument();
    expect(screen.getByText('End user')).toBeInTheDocument();
  });

  it('does not show the project fields at all', () => {
    render(<ComplaintFieldGrid complaint={RETAIL} />);
    expect(screen.queryByText('Delivery Order Number')).toBeNull();
    expect(screen.queryByText('Customer Type')).toBeNull();
    expect(screen.queryByText('Salesperson')).toBeNull();
    expect(screen.queryByText('Project Title')).toBeNull();
  });

  it('shows the site address in the order it is written here', () => {
    render(<ComplaintFieldGrid complaint={RETAIL} />);
    expect(screen.getByText('Site')).toBeInTheDocument();
    expect(screen.getByText('5 Jalan Impiana 1A')).toBeInTheDocument();
    expect(screen.getByText('43000 Kajang')).toBeInTheDocument();
  });

  it('links the pin out without printing the coordinates', () => {
    // Nobody reads a lat/lng off a screen or corrects one by hand; opening it in Maps is
    // the whole of what a dispatcher does with a pin.
    render(<ComplaintFieldGrid complaint={RETAIL} />);
    expect(screen.queryByText(/3\.11843/)).toBeNull();
    expect(screen.getByRole('link', { name: /Open pin/ })).toHaveAttribute(
      'href',
      'https://www.google.com/maps/search/?api=1&query=3.11843%2C101.60210',
    );
  });

  it('states the site is missing rather than rendering nothing', () => {
    // A section that disappears on missing data reads as "this case has no site", which
    // is the opposite of what it means. The CRUD standard requires the empty state.
    render(
      <ComplaintFieldGrid complaint={complaint({ reported_by_role: 'end_user' })} />,
    );
    expect(screen.getByText(/No site address was captured/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Open pin/ })).toBeNull();
  });

  it('shows what the customer called the item beside the code', () => {
    // The code is frequently a guess: SRTWC8152 matches three real variants and resolves
    // to none of them, so the verbatim words are what an agent acts on.
    render(<ComplaintFieldGrid complaint={RETAIL} />);
    expect(screen.getByText('Reported as')).toBeInTheDocument();
    expect(screen.getByText('the toilet in the guest bathroom')).toBeInTheDocument();
    expect(screen.getByText('Leaking since last week.')).toBeInTheDocument();
    expect(screen.getByText('Water Closet')).toBeInTheDocument();
  });

  it('says the purchase is not matched, never that there is no receipt', () => {
    // The consumer very often DID upload one - it is in Linked Attachments - and what is
    // missing is the purchase RECORD the cover computes from. "No receipt" sends CS
    // looking for a file that is already on the page.
    render(<ComplaintFieldGrid complaint={RETAIL} />);
    expect(screen.getByText('Not matched')).toBeInTheDocument();
    expect(screen.queryByText(/No receipt/)).toBeNull();
  });

  it('shows a matched purchase when there is one', () => {
    render(
      <ComplaintFieldGrid
        complaint={complaint({
          reported_by_role: 'end_user',
          product_lines: [
            {
              product_code: 'SRTWC8152',
              purchase_number: 'CP2026-0001',
              purchase_date: '2026-08-03',
            },
          ],
        })}
      />,
    );
    expect(screen.getByText('CP2026-0001')).toBeInTheDocument();
    expect(screen.queryByText('Not matched')).toBeNull();
  });

  it('offers the original message separately from what was made of it', () => {
    // Folding the burst into the description loses the ability to tell a bad extraction
    // from a badly-worded message.
    render(
      <ComplaintFieldGrid
        complaint={complaint({
          reported_by_role: 'end_user',
          intake_transcript: 'toilet spoil sudah, leaking',
          defect_description: 'Cistern leaking from the base.',
        })}
      />,
    );
    expect(screen.getByText('Original message')).toBeInTheDocument();
    expect(screen.getByText('toilet spoil sudah, leaking')).toBeInTheDocument();
    expect(screen.getByText('What the customer told us')).toBeInTheDocument();
  });
});

describe('a project complaint', () => {
  it('keeps every field it has always had', () => {
    render(<ComplaintFieldGrid complaint={PROJECT} />);
    expect(screen.getByText('Delivery Order Number')).toBeInTheDocument();
    expect(screen.getByText('DO-1')).toBeInTheDocument();
    expect(screen.getByText('Project Title')).toBeInTheDocument();
    expect(screen.getByText('Tower B refit')).toBeInTheDocument();
    expect(screen.getByText('Salesperson')).toBeInTheDocument();
    expect(screen.getByText('Delivery Address')).toBeInTheDocument();
  });

  it('does not grow a site section it has no data for', () => {
    render(<ComplaintFieldGrid complaint={PROJECT} />);
    expect(screen.queryByText('Site')).toBeNull();
    expect(screen.queryByText('Reported by')).toBeNull();
  });

  it('keeps the product type column instead of the consumer ones', () => {
    render(<ComplaintFieldGrid complaint={PROJECT} />);
    expect(screen.getByText('Product type')).toBeInTheDocument();
    expect(screen.queryByText('Reported as')).toBeNull();
    expect(screen.queryByText('Kind')).toBeNull();
  });

  it('still splits the legacy CSV columns for rows written before product lines', () => {
    render(
      <ComplaintFieldGrid
        complaint={complaint({
          product_code: 'A-1, B-2',
          product_type: 'Sanitary, Tap',
          quantity: '2, 3',
        })}
      />,
    );
    expect(screen.getByText('A-1')).toBeInTheDocument();
    expect(screen.getByText('B-2')).toBeInTheDocument();
    expect(screen.getByText('Tap')).toBeInTheDocument();
  });
});

describe('a complaint with no products at all', () => {
  it('says so instead of rendering an empty table', () => {
    render(<ComplaintFieldGrid complaint={complaint({ reported_by_role: 'end_user' })} />);
    expect(screen.getByText(/No products recorded/)).toBeInTheDocument();
  });
});

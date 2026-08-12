/**
 * RevisionSnapshotDialog - the whole form as it stood at one revision.
 *
 * Rendered from the entry's own `snapshot_fields` (labeled by the backend),
 * never from the live row: the reader sees the values AS THEY WERE at that
 * version. Read only - no inputs, no actions.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { RevisionSnapshotDialog } from './RevisionSnapshotDialog';
import type { FormRevisionEntry } from './RevisionTimeline';

function entry(overrides: Partial<FormRevisionEntry> = {}): FormRevisionEntry {
  return {
    id: 'rev-1',
    version_no: 1,
    revision_no: 1,
    kind: 'revision',
    label: 'Revision 1',
    reason: 'Wrong quantity',
    submitted_at: '2026-08-01T02:00:00',
    submitted_by: 'Darren Lee',
    snapshot_fields: [
      { field: 'inquiry_number', label: 'Inquiry number', value: 'SI-26-0184', display: null },
      { field: 'product_code', label: 'Product code', value: 'SRTWT51030', display: null },
      { field: 'quantity', label: 'Quantity', value: '4', display: null },
      {
        field: 'delivery_date',
        label: 'Delivery date',
        value: '2026-08-20',
        display: '20/08/2026',
      },
      { field: 'remark', label: 'Remark', value: null, display: null },
    ],
    ...overrides,
  };
}

describe('RevisionSnapshotDialog', () => {
  it('renders nothing when no entry is selected', () => {
    render(<RevisionSnapshotDialog entry={null} onOpenChange={() => {}} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders every field with its label and the value as it was', () => {
    render(<RevisionSnapshotDialog entry={entry()} onOpenChange={() => {}} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Revision 1')).toBeInTheDocument();
    expect(screen.getByText('Inquiry number')).toBeInTheDocument();
    expect(screen.getByText('SI-26-0184')).toBeInTheDocument();
    expect(screen.getByText('Product code')).toBeInTheDocument();
    expect(screen.getByText('SRTWT51030')).toBeInTheDocument();
    expect(screen.getAllByTestId('snapshot-field')).toHaveLength(5);
  });

  it('shows an explicit empty state for a field with no value, never hides it', () => {
    render(<RevisionSnapshotDialog entry={entry()} onOpenChange={() => {}} />);

    expect(screen.getByText('Remark')).toBeInTheDocument();
    expect(screen.getByText('Not provided')).toBeInTheDocument();
  });

  it('names who sent the version and when', () => {
    render(<RevisionSnapshotDialog entry={entry()} onOpenChange={() => {}} />);
    expect(screen.getByText(/by Darren Lee/)).toBeInTheDocument();
  });

  it('renders line items as a table, one row per product', () => {
    render(
      <RevisionSnapshotDialog
        entry={entry({
          snapshot_fields: [
            { field: 'project_title', label: 'Project title', value: 'Showroom' },
            {
              field: 'products',
              label: 'Products',
              value: [
                {
                  item_code: 'SRTWT51030',
                  quantity: '2',
                  unit_price: '1200',
                  total: '2400',
                  remark: null,
                },
                {
                  item_code: 'SRTBT2201',
                  quantity: '1',
                  unit_price: '800',
                  total: '800',
                  remark: 'White',
                },
              ],
            },
          ],
        })}
        onOpenChange={() => {}}
      />,
    );

    expect(screen.getByText('Products')).toBeInTheDocument();
    expect(screen.getAllByTestId('snapshot-product-row')).toHaveLength(2);
    expect(screen.getByText('SRTBT2201')).toBeInTheDocument();
    expect(screen.getByText('White')).toBeInTheDocument();
  });

  it('shows the date the backend rendered, not the raw ISO string it stored', () => {
    render(
      <RevisionSnapshotDialog
        entry={entry({
          snapshot_fields: [
            {
              field: 'delivery_date',
              label: 'Delivery date',
              value: '2026-08-20',
              display: '20/08/2026',
            },
          ],
        })}
        onOpenChange={() => {}}
      />,
    );

    expect(screen.getByText('20/08/2026')).toBeInTheDocument();
    expect(screen.queryByText('2026-08-20')).toBeNull();
  });

  it('shows the display the backend rendered for a lookup code, never the code', () => {
    render(
      <RevisionSnapshotDialog
        entry={entry({
          snapshot_fields: [
            {
              field: 'sales_type',
              label: 'Sales type',
              value: 'cash_sales',
              display: 'Cash sales',
            },
          ],
        })}
        onOpenChange={() => {}}
      />,
    );

    expect(screen.getByText('Cash sales')).toBeInTheDocument();
    expect(screen.queryByText('cash_sales')).toBeNull();
  });

  it('falls back to the stored value for a field the backend added no display to', () => {
    render(
      <RevisionSnapshotDialog
        entry={entry({
          snapshot_fields: [
            { field: 'project_name', label: 'Project name', value: 'Showroom KL', display: null },
            { field: 'remark', label: 'Remark', value: 'Deliver after 5pm' },
          ],
        })}
        onOpenChange={() => {}}
      />,
    );

    expect(screen.getByText('Showroom KL')).toBeInTheDocument();
    expect(screen.getByText('Deliver after 5pm')).toBeInTheDocument();
  });

  it('lists the files as they stood at this version, including one a later revision removed', () => {
    render(
      <RevisionSnapshotDialog
        entry={entry({
          attachments: [
            { attachment_id: 'att-1', filename: 'quote.pdf' },
            { attachment_id: 'att-2', filename: 'dropped-later.jpg' },
          ],
        })}
        onOpenChange={() => {}}
      />,
    );

    expect(screen.getAllByTestId('snapshot-attachment')).toHaveLength(2);
    expect(screen.getByText('quote.pdf')).toBeInTheDocument();
    expect(screen.getByText('dropped-later.jpg')).toBeInTheDocument();
  });

  it('renders the attachments section with an explicit empty state, never hidden', () => {
    render(<RevisionSnapshotDialog entry={entry({ attachments: [] })} onOpenChange={() => {}} />);

    expect(screen.getByText('Attachments')).toBeInTheDocument();
    expect(screen.getByText('None')).toBeInTheDocument();
  });

  it('contains no form controls: the view is read only', () => {
    render(<RevisionSnapshotDialog entry={entry()} onOpenChange={() => {}} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog.querySelectorAll('input, textarea, select')).toHaveLength(0);
  });

  it('reports the close request through onOpenChange', () => {
    const onOpenChange = vi.fn();
    render(<RevisionSnapshotDialog entry={entry()} onOpenChange={onOpenChange} />);
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

/**
 * P4 - the header the extraction read (AC-D2), editable before it binds (AC-D3).
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { POVersionHeader } from '../../_shared/types/poIntake.types';
import { POIntakeHeaderFields } from './POIntakeHeaderFields';

function header(overrides: Partial<POVersionHeader> = {}): POVersionHeader {
  return {
    po_number: 'HQ/26/01/041',
    po_date: '2026-01-19',
    term_days: 60,
    sales_person: 'Ali Hassan',
    customer_order_ref: 'BUI/TR/2026/0114',
    admin_ref: 'PS26-0143',
    remark: null,
    ...overrides,
  };
}

const onSave = vi.fn(async () => {});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('POIntakeHeaderFields', () => {
  it('shows every field it read, and the ones it did not as blank', () => {
    render(
      <POIntakeHeaderFields
        header={header({ sales_person: null })}
        readOnly={false}
        saving={false}
        onSave={onSave}
      />,
    );

    expect(screen.getByLabelText('PO number')).toHaveValue('HQ/26/01/041');
    expect(screen.getByLabelText('Term (days)')).toHaveValue(60);
    expect(screen.getByLabelText('Salesperson')).toHaveValue('');
    expect(screen.getByLabelText('Salesperson')).toHaveAttribute('placeholder', 'Not read');
  });

  it('cannot be saved until something changed, and can be undone', () => {
    render(
      <POIntakeHeaderFields
        header={header()}
        readOnly={false}
        saving={false}
        onSave={onSave}
      />,
    );

    expect(screen.getByRole('button', { name: 'Save header' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: /Undo changes/i })).toBeNull();

    fireEvent.change(screen.getByLabelText('PO number'), {
      target: { value: 'HQ/26/01/141' },
    });
    expect(screen.getByRole('button', { name: 'Save header' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: /Undo changes/i }));
    expect(screen.getByLabelText('PO number')).toHaveValue('HQ/26/01/041');
    expect(screen.getByRole('button', { name: 'Save header' })).toBeDisabled();
  });

  it('saves the corrected header as one block', async () => {
    render(
      <POIntakeHeaderFields
        header={header()}
        readOnly={false}
        saving={false}
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText('PO number'), {
      target: { value: 'HQ/26/01/141' },
    });
    fireEvent.change(screen.getByLabelText('Term (days)'), { target: { value: '90' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save header' }));

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        po_number: 'HQ/26/01/141',
        po_date: '2026-01-19',
        term_days: 90,
        sales_person: 'Ali Hassan',
        customer_order_ref: 'BUI/TR/2026/0114',
        admin_ref: 'PS26-0143',
        remark: null,
      }),
    );
  });

  it('reads back a confirmed header, naming the fields the document did not carry', () => {
    render(
      <POIntakeHeaderFields
        header={header({ remark: null, sales_person: null })}
        readOnly
        saving={false}
        onSave={onSave}
      />,
    );

    expect(screen.queryByLabelText('PO number')).toBeNull();
    expect(screen.getByText('HQ/26/01/041')).toBeInTheDocument();
    expect(screen.getAllByText('Not on the document')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'Save header' })).toBeNull();
  });
});

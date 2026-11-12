/**
 * AFTER-SALES-P1 red tests (UAC F2): one dialog for create and edit.
 *
 * Contract: `./TechnicianFormDialog` default export, props
 *   { open: boolean; onOpenChange: (o: boolean) => void; technician?: Technician | null;
 *     onSubmit: (v: { name: string; phone: string | null; employment_type: 'employee' | 'contractor' }) => void | Promise<void>;
 *     isSubmitting?: boolean }
 * Labelled fields: Name, Phone, Type (Employee / Contractor). Submit button "Save".
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

import TechnicianFormDialog from './TechnicianFormDialog';

const TECH = { id: 't-1', name: 'Ali Hassan', phone: '+60123456789', employment_type: 'contractor', is_active: true };

function setup(technician?: typeof TECH | null) {
  const onSubmit = vi.fn();
  const view = render(
    <TechnicianFormDialog open onOpenChange={() => {}} technician={technician} onSubmit={onSubmit} />,
  );
  return { onSubmit, view };
}

describe('TechnicianFormDialog (F2)', () => {
  it('create and edit show the same fields', () => {
    const create = setup();
    const createLabels = ['Name', 'Phone', 'Type'].map((l) => !!screen.queryByText(l));
    create.view.unmount();
    setup(TECH);
    const editLabels = ['Name', 'Phone', 'Type'].map((l) => !!screen.queryByText(l));
    expect(createLabels).toEqual([true, true, true]);
    expect(editLabels).toEqual(createLabels);
  });

  it('edit pre-fills the technician', () => {
    setup(TECH);
    expect(screen.getByLabelText('Name')).toHaveValue('Ali Hassan');
    expect(screen.getByLabelText('Phone')).toHaveValue('12-345 6789');
    expect(screen.getByRole('dialog').textContent).toMatch(/Contractor/);
  });

  it('create starts empty', () => {
    setup();
    expect(screen.getByLabelText('Name')).toHaveValue('');
  });

  it('name is required', async () => {
    const { onSubmit } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await new Promise((r) => setTimeout(r, 30));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('create submits trimmed name with the default type Employee', async () => {
    const { onSubmit } = setup();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: '  Siti  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ name: 'Siti', employment_type: 'employee' });
  });

  it('edit submits the changed values and keeps the type', async () => {
    const { onSubmit } = setup(TECH);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Ali H' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ name: 'Ali H', employment_type: 'contractor' });
  });
});

describe('TechnicianFormDialog phone (F2: the project-sales PhoneInput)', () => {
  it('renders the shared PhoneInput with its country picker', () => {
    setup();
    expect(screen.getByRole('dialog').querySelector('input[type="text"], input')).not.toBeNull();
    expect(screen.getByRole('dialog').textContent).toMatch(/\+60/);
  });

  it('blocks Save on an incomplete number and says why', async () => {
    const { onSubmit } = setup();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Siti' } });
    fireEvent.change(screen.getByLabelText('Phone'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.getByRole('dialog').textContent).toMatch(/Enter a valid phone number, e\.g\. 12-345 6789\./));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits the number as E.164', async () => {
    const { onSubmit } = setup();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Siti' } });
    fireEvent.change(screen.getByLabelText('Phone'), { target: { value: '123456789' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].phone).toBe('+60123456789');
  });
});

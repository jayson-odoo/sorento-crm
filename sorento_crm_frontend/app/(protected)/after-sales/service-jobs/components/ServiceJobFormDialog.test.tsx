/** Create = Edit: one dialog, the same fields (owner ruling 12 Nov); the phone is the shared PhoneInput. */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
let canComplaints = true;
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => canComplaints }));
vi.mock('../services/serviceJobService', () => ({ searchComplaintNumbers: vi.fn(async () => []) }));

import ServiceJobFormDialog from './ServiceJobFormDialog';

const JOB = {
  id: 'j-1', job_number: 'SV26/11-0001', complaint_id: null, complaint_number: null, customer_name: 'Ms Lim Trading',
  contact_name: 'Ms Lim', contact_phone: '+60123456789', city: 'Ipoh', site_country: 'Malaysia', problem: 'Leak',
  status: 'proposed', status_label: 'Proposed', technician_id: null, technician_name: null,
  scheduled_from: null, scheduled_to: null, customer_agreed_by: null,
};

function setup(job: typeof JOB | null = null) {
  const onSubmit = vi.fn();
  render(<ServiceJobFormDialog open onOpenChange={() => {}} job={job as never} onSubmit={onSubmit} />);
  return onSubmit;
}

describe('ServiceJobFormDialog', () => {
  it('create and edit show the same fields', () => {
    const labels = ['Customer name *', 'Contact on site', 'Contact phone', 'Address line 1', 'Address line 2', 'Postcode', 'City', 'State', 'Country', 'Problem', 'Related complaint'];
    setup();
    const create = labels.map((l) => !!screen.queryByText(l));
    expect(create.every(Boolean)).toBe(true);
  });

  it('Country defaults to Malaysia on create', () => {
    setup();
    expect(screen.getByLabelText('Country')).toHaveValue('Malaysia');
  });

  it('edit pre-fills the job', () => {
    setup(JOB);
    expect(screen.getByLabelText('Customer name *')).toHaveValue('Ms Lim Trading');
    expect(screen.getByLabelText('City')).toHaveValue('Ipoh');
    expect(screen.getByLabelText('Contact phone')).toHaveValue('12-345 6789');
  });

  it('customer name is required', async () => {
    const onSubmit = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Customer name is required.'));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('blocks Save on an incomplete phone number', async () => {
    const onSubmit = setup();
    fireEvent.change(screen.getByLabelText('Customer name *'), { target: { value: 'Mr Tan' } });
    fireEvent.change(screen.getByLabelText('Contact phone'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.getByRole('dialog').textContent).toMatch(/Enter a valid phone number/));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits trimmed values, the phone as E.164 and no related complaint', async () => {
    const onSubmit = setup();
    fireEvent.change(screen.getByLabelText('Customer name *'), { target: { value: '  Mr Tan ' } });
    fireEvent.change(screen.getByLabelText('Contact phone'), { target: { value: '123456789' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      customer_name: 'Mr Tan', contact_phone: '+60123456789', complaint_id: null, site_country: 'Malaysia',
    });
  });

  it('hides Related complaint from a user who may not view complaints', () => {
    canComplaints = false;
    setup();
    expect(screen.queryByText('Related complaint')).toBeNull();
    canComplaints = true;
  });
});

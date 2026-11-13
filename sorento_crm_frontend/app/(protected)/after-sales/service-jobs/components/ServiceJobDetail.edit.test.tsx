/**
 * R7-1: the job page's gear > Edit must save. The dialog is opened through the gear item exactly as
 * the page does; Save has to call the update with the change and toast success.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/after-sales/service-jobs/j-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: Omit<import('react').ComponentProps<'a'>, 'href'> & { href?: unknown }) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>
  ),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/components/common/RecordNavigation', () => ({ default: () => null, RecordNavigation: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => null }));

// The REAL mutation hook and toast, over a mocked service: the request is the update function.
const toastSuccess = vi.fn();
vi.mock('@/lib/toast', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn(), warning: vi.fn() } }));
const updateServiceJob = vi.fn(async () => ({}));
vi.mock('../services/serviceJobService', async (orig) => ({
  ...(await orig<object>()),
  updateServiceJob: (...a: unknown[]) => updateServiceJob(...a),
  getServiceJob: vi.fn(),
  searchComplaintNumbers: vi.fn(async () => []),
}));
const useServiceJob = vi.fn();
vi.mock('../hooks/useServiceJobs', async (orig) => ({
  ...(await orig<object>()),
  useServiceJob: (...a: unknown[]) => useServiceJob(...a),
}));

import ServiceJobDetail from './ServiceJobDetail';

const JOB = {
  id: 'j-1', job_number: 'SV26/11-0001', complaint_id: null, complaint_number: null, customer_name: 'Ms Lim Trading',
  contact_name: 'Ms Lim', contact_phone: '+60123456789', contact_phone_display: '012-345 6789', city: 'Ipoh',
  site_address_line1: '1 Jalan A', site_country: 'Malaysia', problem: 'Leak',
  status: 'proposed', status_label: 'Proposed', technician_id: null, technician_name: null,
  scheduled_from: null, scheduled_to: null, customer_agreed_by: null,
};

async function openEditFromGear() {
  render(<QueryClientProvider client={new QueryClient()}><ServiceJobDetail jobId="j-1" /></QueryClientProvider>);
  const gear = screen.getByRole('button', { name: 'Service job actions' });
  fireEvent.pointerDown(gear, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(gear, { button: 0, pointerId: 1 });
  fireEvent.click(gear);
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }));
  return screen.findByRole('dialog');
}

beforeEach(() => {
  updateServiceJob.mockClear();
  toastSuccess.mockClear();
  useServiceJob.mockReturnValue({ data: JOB, isLoading: false });
});

describe('job page gear > Edit, with real pointer events', () => {
  it('saves after the gear item opened the dialog (click sequence as a user makes it)', async () => {
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient()}><ServiceJobDetail jobId="j-1" /></QueryClientProvider>);
    await user.click(screen.getByRole('button', { name: 'Service job actions' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Edit' }));
    const city = await screen.findByLabelText('City');
    await new Promise((r) => setTimeout(r, 800)); // a person takes longer than the open-grace window
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await user.clear(city);
    await user.type(city, 'Klang');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateServiceJob).toHaveBeenCalledTimes(1));
    expect(updateServiceJob.mock.calls[0][1]).toMatchObject({ site_city: 'Klang' });
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  });
});

describe('job page gear > Edit, a stored number libphonenumber does not call valid', () => {
  it('still saves when the phone is left untouched', async () => {
    useServiceJob.mockReturnValue({ data: { ...JOB, contact_phone: '+60170000502', contact_phone_display: '017-000 0502' }, isLoading: false });
    await openEditFromGear();
    fireEvent.change(screen.getByLabelText('City'), { target: { value: 'Klang' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateServiceJob).toHaveBeenCalledTimes(1));
    expect(updateServiceJob.mock.calls[0][1]).toMatchObject({ site_city: 'Klang', contact_phone: '+60170000502' });
  });
});

describe('job page gear > Edit', () => {
  it('keeps what was typed when the page re-renders with a refetched job object', async () => {
    useServiceJob.mockImplementation(() => ({ data: { ...JOB }, isLoading: false })); // a new object every call
    const view = render(<QueryClientProvider client={new QueryClient()}><ServiceJobDetail jobId="j-1" /></QueryClientProvider>);
    const gear = screen.getByRole('button', { name: 'Service job actions' });
    fireEvent.pointerDown(gear, { button: 0, pointerId: 1 });
    fireEvent.pointerUp(gear, { button: 0, pointerId: 1 });
    fireEvent.click(gear);
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }));
    fireEvent.change(await screen.findByLabelText('City'), { target: { value: 'Klang' } });
    view.rerender(<QueryClientProvider client={new QueryClient()}><ServiceJobDetail jobId="j-1" /></QueryClientProvider>);
    expect(screen.getByLabelText('City')).toHaveValue('Klang');
  });

  it('saves a changed field: one update request with the change, and a success toast', async () => {
    await openEditFromGear();
    fireEvent.change(screen.getByLabelText('City'), { target: { value: 'Klang' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateServiceJob).toHaveBeenCalledTimes(1));
    expect(updateServiceJob.mock.calls[0]).toEqual(['j-1', expect.objectContaining({ site_city: 'Klang', customer_name: 'Ms Lim Trading' })]);
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  });

  it('saves with the prefilled phone unchanged, sending it as E.164', async () => {
    await openEditFromGear();
    expect(screen.getByLabelText('Contact phone')).toHaveValue('12-345 6789');
    fireEvent.change(screen.getByLabelText('Customer name *'), { target: { value: 'Ms Lim Trading Sdn Bhd' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateServiceJob).toHaveBeenCalledTimes(1));
    expect(updateServiceJob.mock.calls[0][1]).toMatchObject({ contact_phone: '+60123456789' });
  });

  it('stays open and says why when the customer name is cleared', async () => {
    await openEditFromGear();
    fireEvent.change(screen.getByLabelText('Customer name *'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Customer name is required.');
    expect(updateServiceJob).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

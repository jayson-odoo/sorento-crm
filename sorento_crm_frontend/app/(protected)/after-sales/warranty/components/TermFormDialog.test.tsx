/**
 * AFTER-SALES-P2 red tests (UAC C3, F3): add and edit a policy term.
 *
 * Module the coder builds: `./TermFormDialog`, named export `TermFormDialog`, props
 *   { open, onOpenChange(open), policyId: string, term?: WarrantyTerm | null }   (term set = Edit)
 * A centred dialog (role dialog). Fields in order, each with its label as accessible name:
 *   Kind (SearchableSelect, aria-label "Kind", options from useKindOptions; disabled when editing, the API does not
 *   move a term to another kind), Part (text input), Cover = a "Lifetime" checkbox AND a "Months" number input (never
 *   both, never neither: checked on save, the error shown next to the field, nothing sent), Defects
 *   (SearchableMultiSelect, aria-label "Defects", clearable, options from useDefectOptions, empty = all defects
 *   = sent as null), Installation included (checkbox). Buttons Cancel and "Create" (new) / "Save" (edit).
 * Errors, exact: neither -> "Enter the months or tick Lifetime"; both -> "Lifetime has no months: clear one of them".
 * Service calls (`../services/warrantyConfigService`, mocked here; the hooks stay real):
 *   createTerm({ policy_id, kind_id, part_name, duration_months, is_lifetime, covered_defect_type_ids: string[] | null,
 *                installation_included })        -> POST /api/v1/after-sales/warranty/terms
 *   updateTerm(id, { part_name, duration_months, is_lifetime, covered_defect_type_ids, installation_included })
 *                                                 -> PATCH .../terms/{id}   (no kind_id, no policy_id)
 * The dialog closes (onOpenChange(false)) after a successful save and stays open when the save fails.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

type Opt = { value: string; label: string };
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: { value: string; onChange: (v: string) => void; options?: Opt[]; disabled?: boolean; 'aria-label'?: string }) => (
    <select aria-label={p['aria-label']} value={p.value} disabled={p.disabled} onChange={(e) => p.onChange(e.target.value)}>
      <option value="">-</option>
      {(p.options ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (p: { value: string[]; onChange: (v: string[]) => void; options?: Opt[]; clearable?: boolean; 'aria-label'?: string }) => (
    <div role="group" aria-label={p['aria-label']}>
      {(p.options ?? []).map((o) => (
        <button
          key={o.value}
          type="button"
          aria-label={`Defect ${o.label}`}
          aria-pressed={p.value.includes(o.value)}
          onClick={() => p.onChange(p.value.includes(o.value) ? p.value.filter((v) => v !== o.value) : [...p.value, o.value])}
        />
      ))}
      {p.clearable && p.value.length ? <button type="button" aria-label="Clear Defects" onClick={() => p.onChange([])} /> : null}
    </div>
  ),
}));

const svc = vi.hoisted(() => ({ createTerm: vi.fn(), updateTerm: vi.fn() }));
vi.mock('../services/warrantyConfigService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  createTerm: svc.createTerm,
  updateTerm: svc.updateTerm,
  getKinds: vi.fn(async () => ({
    data: [{ id: 'k-1', code: 'WC', name: 'Water Closet' }, { id: 'k-2', code: 'MC', name: 'Mirror Cabinet' }],
    pagination: { total: 2, page: 1, limit: 200 },
  })),
  getDefectTypes: vi.fn(async () => [{ id: 'd-1', label: 'Crack line' }, { id: 'd-2', label: 'Leakage' }]),
}));

import { TermFormDialog } from './TermFormDialog';

const TERM = {
  id: 't-2', policy_id: 'pol-15', kind_id: 'k-1', part_name: 'Flushing Fittings', duration_months: 60, is_lifetime: false,
  covered_defect_type_ids: ['d-2'], installation_included: true, qualifications: null, exclusions: null,
};
const onOpenChange = vi.fn();
const setup = (term: unknown = null) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TermFormDialog open onOpenChange={onOpenChange} policyId="pol-15" term={term as never} />
    </QueryClientProvider>,
  );
const pickKind = async (name: string) => {
  await screen.findByRole('option', { name });
  fireEvent.change(screen.getByLabelText('Kind'), { target: { value: name === 'Water Closet' ? 'k-1' : 'k-2' } });
};

beforeEach(() => {
  vi.clearAllMocks();
  svc.createTerm.mockResolvedValue({});
  svc.updateTerm.mockResolvedValue({});
});

describe('TermFormDialog', () => {
  it('is a dialog with Kind, Part, Lifetime, Months, Defects and Installation included, and Cancel and Create', async () => {
    setup();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await screen.findByRole('option', { name: 'Water Closet' });
    for (const label of ['Kind', 'Part', 'Lifetime', 'Months', 'Installation included']) expect(screen.getByLabelText(label)).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Defects' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument();
  });

  it('a months term is created with the policy id, and empty defects go as null', async () => {
    setup();
    await pickKind('Water Closet');
    fireEvent.change(screen.getByLabelText('Part'), { target: { value: 'Seat Cover' } });
    fireEvent.change(screen.getByLabelText('Months'), { target: { value: '24' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(svc.createTerm).toHaveBeenCalledTimes(1));
    expect(svc.createTerm.mock.calls[0][0]).toMatchObject({
      policy_id: 'pol-15', kind_id: 'k-1', part_name: 'Seat Cover', duration_months: 24, is_lifetime: false,
      covered_defect_type_ids: null, installation_included: false,
    });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('a lifetime term sends no months', async () => {
    setup();
    await pickKind('Water Closet');
    fireEvent.change(screen.getByLabelText('Part'), { target: { value: 'Ceramic Body' } });
    fireEvent.click(screen.getByLabelText('Lifetime'));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(svc.createTerm).toHaveBeenCalled());
    expect(svc.createTerm.mock.calls[0][0]).toMatchObject({ is_lifetime: true, duration_months: null });
  });

  it('chosen defects and Installation included are sent, and clearing the defects sends null again', async () => {
    setup();
    await pickKind('Water Closet');
    fireEvent.change(screen.getByLabelText('Part'), { target: { value: 'Ceramic Body' } });
    fireEvent.click(screen.getByLabelText('Lifetime'));
    fireEvent.click(screen.getByLabelText('Installation included'));
    fireEvent.click(screen.getByRole('button', { name: 'Defect Crack line' }));
    fireEvent.click(screen.getByRole('button', { name: 'Defect Leakage' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(svc.createTerm).toHaveBeenCalledTimes(1));
    expect(svc.createTerm.mock.calls[0][0]).toMatchObject({ covered_defect_type_ids: ['d-1', 'd-2'], installation_included: true });
    fireEvent.click(screen.getByRole('button', { name: 'Clear Defects' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(svc.createTerm).toHaveBeenCalledTimes(2));
    expect(svc.createTerm.mock.calls[1][0]).toMatchObject({ covered_defect_type_ids: null });
  });

  it('neither Lifetime nor Months is refused next to the field and nothing is sent', async () => {
    setup();
    await pickKind('Water Closet');
    fireEvent.change(screen.getByLabelText('Part'), { target: { value: 'Seat Cover' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(await screen.findByText('Enter the months or tick Lifetime')).toBeInTheDocument();
    expect(svc.createTerm).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('zero months counts as no months', async () => {
    setup();
    await pickKind('Water Closet');
    fireEvent.change(screen.getByLabelText('Part'), { target: { value: 'Seat Cover' } });
    fireEvent.change(screen.getByLabelText('Months'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(await screen.findByText('Enter the months or tick Lifetime')).toBeInTheDocument();
    expect(svc.createTerm).not.toHaveBeenCalled();
  });

  it('Lifetime together with Months is refused and nothing is sent', async () => {
    setup();
    await pickKind('Water Closet');
    fireEvent.change(screen.getByLabelText('Part'), { target: { value: 'Seat Cover' } });
    fireEvent.change(screen.getByLabelText('Months'), { target: { value: '24' } });
    fireEvent.click(screen.getByLabelText('Lifetime'));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(await screen.findByText('Lifetime has no months: clear one of them')).toBeInTheDocument();
    expect(svc.createTerm).not.toHaveBeenCalled();
  });

  it('Kind and Part are required', async () => {
    setup();
    fireEvent.change(await screen.findByLabelText('Months'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(screen.getAllByText(/required/i).length).toBeGreaterThanOrEqual(2));
    expect(svc.createTerm).not.toHaveBeenCalled();
  });

  it('a failed save keeps the dialog open', async () => {
    svc.createTerm.mockRejectedValue(new Error('Duplicate part'));
    setup();
    await pickKind('Water Closet');
    fireEvent.change(screen.getByLabelText('Part'), { target: { value: 'Seat Cover' } });
    fireEvent.change(screen.getByLabelText('Months'), { target: { value: '24' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(svc.createTerm).toHaveBeenCalled());
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('edit: prefilled, Kind locked, Save PATCHes only the editable fields', async () => {
    setup(TERM);
    await screen.findByRole('option', { name: 'Water Closet' });
    expect((screen.getByLabelText('Kind') as HTMLSelectElement).value).toBe('k-1');
    expect(screen.getByLabelText('Kind')).toBeDisabled();
    expect((screen.getByLabelText('Part') as HTMLInputElement).value).toBe('Flushing Fittings');
    expect((screen.getByLabelText('Months') as HTMLInputElement).value).toBe('60');
    expect(screen.getByLabelText('Installation included')).toBeChecked();
    expect(screen.getByRole('button', { name: 'Defect Leakage' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.change(screen.getByLabelText('Months'), { target: { value: '36' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(svc.updateTerm).toHaveBeenCalledTimes(1));
    const [id, values] = svc.updateTerm.mock.calls[0];
    expect(id).toBe('t-2');
    expect(values).toMatchObject({ part_name: 'Flushing Fittings', duration_months: 36, is_lifetime: false, covered_defect_type_ids: ['d-2'], installation_included: true });
    expect(values).not.toHaveProperty('kind_id');
    expect(values).not.toHaveProperty('policy_id');
    expect(svc.createTerm).not.toHaveBeenCalled();
  });
});

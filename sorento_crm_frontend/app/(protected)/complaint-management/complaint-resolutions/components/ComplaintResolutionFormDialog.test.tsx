/**
 * The switch that decides whether a van is sent.
 *
 * Agnes picks a resolution on a complaint; she should not ALSO have to remember which
 * resolutions mean a technician travels, because that table lived only in her head. Moving
 * it onto the resolution makes it an admin's decision, once, in the open - which only works
 * if this dialog actually round-trips the flag.
 *
 * The default matters as much as the field: a resolution an admin adds and forgets to
 * configure must dispatch NOBODY. The opposite default sends a van by omission.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ComplaintResolutionFormDialog from './ComplaintResolutionFormDialog';
import type { ComplaintResolution } from '../types/complaintResolution.types';

const createMutate = vi.fn();
const updateMutate = vi.fn();
const useComplaintResolution = vi.fn();

vi.mock('../hooks/useComplaintResolutions', () => ({
  useCreateComplaintResolution: () => ({ mutateAsync: createMutate, isPending: false }),
  useUpdateComplaintResolution: () => ({ mutateAsync: updateMutate, isPending: false }),
  useComplaintResolution: (...args: unknown[]) => useComplaintResolution(...args),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function row(overrides: Partial<ComplaintResolution> = {}): ComplaintResolution {
  return {
    id: 'r1',
    name: 'Repair',
    description: null,
    is_active: true,
    requires_service_job: false,
    created_at: '2026-08-08T00:00:00',
    ...overrides,
  };
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintResolutionFormDialog open rowId="r1" onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
}

describe('the raises-a-service-job switch', () => {
  it('is offered, and says what it does rather than what a service job is', () => {
    useComplaintResolution.mockReturnValue({ data: row(), isLoading: false });
    renderDialog();
    expect(screen.getByText('Raises a service job')).toBeInTheDocument();
    expect(
      screen.getByText('Choosing this resolution sends somebody to the site.'),
    ).toBeInTheDocument();
  });

  it('reflects a resolution that already requires a visit', async () => {
    useComplaintResolution.mockReturnValue({
      data: row({ requires_service_job: true }),
      isLoading: false,
    });
    renderDialog();
    await waitFor(() =>
      expect(
        screen.getAllByRole('switch').some((s) => s.getAttribute('data-state') === 'checked'),
      ).toBe(true),
    );
  });

  it('treats a row that predates the column as not requiring a visit', async () => {
    // Every existing row is false by migration, but a response from a stale cache or an
    // older backend can still arrive without the field. Undefined must not read as "yes".
    useComplaintResolution.mockReturnValue({
      data: { ...row(), requires_service_job: undefined } as unknown as ComplaintResolution,
      isLoading: false,
    });
    renderDialog();
    await waitFor(() => expect(screen.getAllByRole('switch').length).toBeGreaterThan(0));
    const switches = screen.getAllByRole('switch');
    // Two switches: Active (true) and Raises a service job (must be false).
    expect(switches.filter((s) => s.getAttribute('data-state') === 'checked')).toHaveLength(1);
  });
});

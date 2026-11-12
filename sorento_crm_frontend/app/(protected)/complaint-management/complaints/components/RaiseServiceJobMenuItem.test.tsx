/** AFTER-SALES-P1 fix round 2 (R2-1): the gear offers "Raise service job" only when the complaint has no live job. */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';

const jobs = vi.fn();
const raise = vi.fn();
let canDispatch = true;
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => canDispatch }));
vi.mock('../../service-jobs/hooks/useServiceJobs', () => ({
  useComplaintServiceJobs: () => jobs(),
  useRaiseServiceJob: () => ({ mutate: raise, isPending: false }),
}));

import RaiseServiceJobMenuItem from './RaiseServiceJobMenuItem';

function setup() {
  return render(
    <DropdownMenu open>
      <DropdownMenuTrigger>gear</DropdownMenuTrigger>
      <DropdownMenuContent>
        <RaiseServiceJobMenuItem complaintId="c-1" />
      </DropdownMenuContent>
    </DropdownMenu>,
  );
}

beforeEach(() => {
  jobs.mockReset();
  raise.mockReset();
  canDispatch = true;
});

describe('RaiseServiceJobMenuItem', () => {
  it('is offered with no job and raises on select', () => {
    jobs.mockReturnValue({ data: [], isLoading: false });
    setup();
    fireEvent.click(screen.getByRole('menuitem', { name: /Raise service job/ }));
    expect(raise).toHaveBeenCalledWith('c-1');
  });

  it.each(['proposed', 'confirmed', 'on_the_way', 'arrived', 'completed'])('is hidden while a %s job is live', (status) => {
    jobs.mockReturnValue({ data: [{ id: 'j', status }], isLoading: false });
    setup();
    expect(screen.queryByRole('menuitem', { name: /Raise service job/ })).toBeNull();
  });

  it.each(['verified', 'cancelled'])('is offered again when the only job is %s', (status) => {
    jobs.mockReturnValue({ data: [{ id: 'j', status }], isLoading: false });
    setup();
    expect(screen.getByRole('menuitem', { name: /Raise service job/ })).toBeInTheDocument();
  });

  it('is hidden while the jobs are still loading, and without the dispatch permission', () => {
    jobs.mockReturnValue({ data: undefined, isLoading: true });
    setup();
    expect(screen.queryByRole('menuitem', { name: /Raise service job/ })).toBeNull();
  });

  it('is hidden without dispatch', () => {
    canDispatch = false;
    jobs.mockReturnValue({ data: [], isLoading: false });
    setup();
    expect(screen.queryByRole('menuitem', { name: /Raise service job/ })).toBeNull();
  });
});

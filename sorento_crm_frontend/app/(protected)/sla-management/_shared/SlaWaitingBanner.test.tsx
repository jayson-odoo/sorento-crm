import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { SlaWaitingBanner } from './SlaWaitingBanner';

const setSlaWaiting = vi.fn();
const clearSlaWaiting = vi.fn();

vi.mock(
  '@/app/(protected)/sla-management/conversation-sla-tracking/services/conversationSLATrackingService',
  () => ({
    setSlaWaiting: (...args: unknown[]) => setSlaWaiting(...args),
    clearSlaWaiting: (...args: unknown[]) => clearSlaWaiting(...args),
  }),
);

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// The two vocabularies come from the lookup binding, which is the whole reason both
// columns store the option VALUE rather than an id. Declared INSIDE the factory: a
// vi.mock factory is hoisted above the module body, so referencing a top-level const
// from it leaves the real module in place and the component hits the network.
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async (path: string) => {
    const options: Record<string, Array<{ value: string; label: string }>> = {
      waiting_on_party: [
        { value: 'plumber', label: 'Plumber' },
        { value: 'maintenance', label: 'Maintenance' },
      ],
      waiting_on_reason: [
        { value: 'pending_plumber', label: 'Pending plumber attendance' },
      ],
    };
    const key = Object.keys(options).find((k) => path.includes(`column=${k}`));
    return {
      ok: true,
      json: async () => ({ options: key ? options[key] : [] }),
    } as unknown as Response;
  }),
}));

beforeEach(() => {
  setSlaWaiting.mockReset();
  clearSlaWaiting.mockReset();
});

describe('SlaWaitingBanner', () => {
  it('reads back the AC-M3 sentence when something is waiting', () => {
    render(
      <SlaWaitingBanner
        trackingId="t1"
        party="maintenance"
        partyLabel="Maintenance"
        waitingSince="2026-08-03T01:00:00"
      />,
    );
    // "waiting on maintenance since 3 Aug", never "stuck at CS".
    expect(screen.getByText(/Waiting on/)).toBeInTheDocument();
    expect(screen.getByText('Maintenance')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /No longer waiting/ })).toBeInTheDocument();
  });

  it('words the prompt as mandatory once the stage is overdue (AC-M4)', () => {
    render(<SlaWaitingBanner trackingId="t1" party={null} overdue />);
    expect(
      screen.getByText(/Say who this is waiting on before you resolve, escalate or extend/),
    ).toBeInTheDocument();
  });

  it('asks without demanding while the stage is still inside its deadline', () => {
    render(<SlaWaitingBanner trackingId="t1" party={null} overdue={false} />);
    expect(screen.getByText(/Waiting on someone outside this stage\?/)).toBeInTheDocument();
    expect(screen.queryByText(/before you resolve/)).not.toBeInTheDocument();
  });

  it('sends the party and clears the editor on save', async () => {
    const onChanged = vi.fn();
    setSlaWaiting.mockResolvedValue(undefined);
    render(<SlaWaitingBanner trackingId="t1" party={null} onChanged={onChanged} />);

    fireEvent.click(screen.getByRole('button', { name: /Record a wait/ }));
    await waitFor(() => expect(screen.getByText('Waiting on')).toBeInTheDocument());

    // Save stays disabled until a party is named: WHO is the mandatory half, the
    // reason is not.
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('surfaces a failed clear rather than pretending the wait ended', async () => {
    clearSlaWaiting.mockRejectedValue(new Error('nope'));
    const onChanged = vi.fn();
    render(
      <SlaWaitingBanner
        trackingId="t1"
        party="plumber"
        partyLabel="Plumber"
        waitingSince="2026-08-03T01:00:00"
        onChanged={onChanged}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /No longer waiting/ }));
    await waitFor(() => expect(clearSlaWaiting).toHaveBeenCalledWith('t1'));
    expect(onChanged).not.toHaveBeenCalled();
  });
});

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { apiFetch } from '@/lib/api';
import { toast } from 'sonner';
import NotificationChannelsPreference from './notification-channels-preference';

const res = (ok: boolean, body: unknown = {}) => ({ ok, json: async () => body }) as Response;

describe('NotificationChannelsPreference (TCK-31 UX1)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads and reflects fetched channel prefs', async () => {
    (apiFetch as any).mockResolvedValueOnce(res(true, { notify_whatsapp: true, notify_whatsapp_summary: false }));
    render(<NotificationChannelsPreference />);
    const escalation = await screen.findByLabelText('Escalation & assignment alerts');
    const summary = screen.getByLabelText('Daily SLA summary');
    await waitFor(() => expect(escalation).toBeChecked());
    expect(summary).not.toBeChecked();
  });

  it('PATCHes the toggled channel', async () => {
    (apiFetch as any).mockResolvedValueOnce(res(true, { notify_whatsapp: false, notify_whatsapp_summary: false }));
    render(<NotificationChannelsPreference />);
    const escalation = await screen.findByLabelText('Escalation & assignment alerts');
    (apiFetch as any).mockResolvedValueOnce(res(true, {}));
    fireEvent.click(escalation);
    await waitFor(() => {
      const patch = (apiFetch as any).mock.calls.find(
        (c: unknown[]) => (c[1] as RequestInit | undefined)?.method === 'PATCH',
      );
      expect(patch).toBeTruthy();
      expect(JSON.parse((patch[1] as RequestInit).body as string)).toEqual({ notify_whatsapp: true });
    });
    expect(toast.success).toHaveBeenCalled();
  });

  it('reverts on PATCH failure', async () => {
    (apiFetch as any).mockResolvedValueOnce(res(true, { notify_whatsapp: false, notify_whatsapp_summary: false }));
    render(<NotificationChannelsPreference />);
    const summary = await screen.findByLabelText('Daily SLA summary');
    (apiFetch as any).mockResolvedValueOnce(res(false));
    fireEvent.click(summary);
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(summary).not.toBeChecked();
  });
});

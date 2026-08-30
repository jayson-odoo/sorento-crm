import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { apiFetch } from '@/lib/api';
import { toast } from 'sonner';
import NotificationChannelsPreference from './notification-channels-preference';

const res = (ok: boolean, body: unknown = {}) => ({ ok, json: async () => body }) as Response;

/**
 * The panel renders the per-event SLA notify matrix: one switch per
 * (channel x event) pair plus the WhatsApp daily-summary toggle. It used to be
 * two coarse switches ("Escalation & assignment alerts" / "Daily SLA summary");
 * these tests were rewritten when the matrix landed.
 */
describe('NotificationChannelsPreference (TCK-31 UX1)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reflects each fetched per-event preference independently', async () => {
    (apiFetch as any).mockResolvedValueOnce(
      res(true, {
        notify_email_on_assignment: true,
        notify_email_on_escalation: false,
        notify_whatsapp_on_assignment: true,
        notify_whatsapp_on_escalation: false,
        notify_whatsapp_summary: true,
      }),
    );
    render(<NotificationChannelsPreference />);

    const emailAssign = await screen.findByLabelText('Email on assignment');
    await waitFor(() => expect(emailAssign).toBeChecked());

    // Each key maps to its own switch - a matrix, not one coarse toggle.
    expect(screen.getByLabelText('Email on escalation')).not.toBeChecked();
    expect(screen.getByLabelText('WhatsApp on assignment')).toBeChecked();
    expect(screen.getByLabelText('WhatsApp on escalation')).not.toBeChecked();
    expect(screen.getByLabelText('WhatsApp daily SLA summary')).toBeChecked();
  });

  it('defaults the email toggles on and the WhatsApp toggles off when absent', async () => {
    (apiFetch as any).mockResolvedValueOnce(res(true, {}));
    render(<NotificationChannelsPreference />);

    const emailAssign = await screen.findByLabelText('Email on assignment');
    await waitFor(() => expect(emailAssign).toBeChecked());

    expect(screen.getByLabelText('Email on escalation')).toBeChecked();
    expect(screen.getByLabelText('Email on deadline extended')).toBeChecked();
    expect(screen.getByLabelText('Email on mention in a note')).toBeChecked();
    expect(screen.getByLabelText('WhatsApp on assignment')).not.toBeChecked();
    expect(screen.getByLabelText('WhatsApp daily SLA summary')).not.toBeChecked();
  });

  it('PATCHes only the toggled key', async () => {
    // Route by request method, not call order: the initial GET and the click's
    // PATCH hit the same URL, and an ordered mockResolvedValueOnce queue misaligns
    // if the mount fetch hasn't settled before the click (the source of the flake).
    (apiFetch as any).mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === 'PATCH'
          ? res(true, {})
          : res(true, { notify_whatsapp_on_escalation: false, notify_email_on_assignment: true }),
      ),
    );
    render(<NotificationChannelsPreference />);

    const waEscalation = await screen.findByLabelText('WhatsApp on escalation');
    // Wait for ENABLED, not merely present. Every switch renders `disabled` until
    // the mount GET settles, React drops clicks on disabled elements entirely, and
    // findBy* resolves as soon as the node exists - so a click here races the load
    // and is silently swallowed, taking the PATCH and the assertions with it.
    await waitFor(() => expect(waEscalation).toBeEnabled());
    fireEvent.click(waEscalation);

    await waitFor(() => {
      const patch = (apiFetch as any).mock.calls.find(
        (c: unknown[]) => (c[1] as RequestInit | undefined)?.method === 'PATCH',
      );
      expect(patch).toBeTruthy();
      // Single-key payload: sending the whole matrix would clobber concurrent edits.
      expect(JSON.parse((patch[1] as RequestInit).body as string)).toEqual({
        notify_whatsapp_on_escalation: true,
      });
    });
    expect(toast.success).toHaveBeenCalled();
  });

  it('PATCHes notify_email_on_mention when the mention row is toggled', async () => {
    // Mention is email-only: there is no WhatsApp twin for this event, so the
    // single row owns the whole opt-in.
    (apiFetch as any).mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === 'PATCH' ? res(true, {}) : res(true, { notify_email_on_mention: true }),
      ),
    );
    render(<NotificationChannelsPreference />);

    const mention = await screen.findByLabelText('Email on mention in a note');
    await waitFor(() => expect(mention).toBeEnabled());
    expect(mention).toBeChecked();
    fireEvent.click(mention);

    await waitFor(() => {
      const patch = (apiFetch as any).mock.calls.find(
        (c: unknown[]) => (c[1] as RequestInit | undefined)?.method === 'PATCH',
      );
      expect(patch).toBeTruthy();
      expect(JSON.parse((patch[1] as RequestInit).body as string)).toEqual({
        notify_email_on_mention: false,
      });
    });
    expect(screen.queryByLabelText('WhatsApp on mention in a note')).toBeNull();
  });

  it('reverts the switch on PATCH failure', async () => {
    // Route by method: GET loads the prefs, the PATCH fails. An ordered
    // mockResolvedValueOnce queue flaked here when the mount GET hadn't consumed
    // its entry before the click fired the PATCH.
    (apiFetch as any).mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === 'PATCH' ? res(false) : res(true, { notify_whatsapp_summary: false }),
      ),
    );
    render(<NotificationChannelsPreference />);

    const summary = await screen.findByLabelText('WhatsApp daily SLA summary');
    // See above: present != interactive. This is the one that actually broke CI.
    await waitFor(() => expect(summary).toBeEnabled());
    fireEvent.click(summary);

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(summary).not.toBeChecked();
  });
});

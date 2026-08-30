import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('@/services/pushService', () => ({
  isPushSupported: vi.fn(),
  getPushState: vi.fn(),
  subscribeToPush: vi.fn(),
  unsubscribeFromPush: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';

import {
  isPushSupported,
  getPushState,
  subscribeToPush,
} from '@/services/pushService';
import PushNotificationPreference from './push-notification-preference';

describe('PushNotificationPreference (TCK-33 UX1)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows Enable when supported + not subscribed, and subscribes on click', async () => {
    (isPushSupported as any).mockReturnValue(true);
    (getPushState as any).mockResolvedValue(false);
    (subscribeToPush as any).mockResolvedValue({ ok: true });
    render(<PushNotificationPreference />);
    const btn = await screen.findByRole('button', { name: /enable notifications/i });
    fireEvent.click(btn);
    await waitFor(() => expect(subscribeToPush).toHaveBeenCalled());
  });

  it('names a blocked push service in the error toast, with the way out', async () => {
    (isPushSupported as any).mockReturnValue(true);
    (getPushState as any).mockResolvedValue(false);
    (subscribeToPush as any).mockResolvedValue({ ok: false, reason: 'push-service-blocked' });
    render(<PushNotificationPreference />);
    fireEvent.click(await screen.findByRole('button', { name: /enable notifications/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const [title, options] = (toast.error as any).mock.calls[0];
    expect(title).toMatch(/push service/i);
    expect(options.description).toMatch(/try again/i);
    expect(toast.success).not.toHaveBeenCalled();
    // Still off, so the button stays the way back in.
    expect(
      await screen.findByRole('button', { name: /enable notifications/i }),
    ).toBeInTheDocument();
  });

  it('tells a user with notifications blocked where to unblock them', async () => {
    (isPushSupported as any).mockReturnValue(true);
    (getPushState as any).mockResolvedValue(false);
    (subscribeToPush as any).mockResolvedValue({ ok: false, reason: 'permission-denied' });
    render(<PushNotificationPreference />);
    fireEvent.click(await screen.findByRole('button', { name: /enable notifications/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const [title, options] = (toast.error as any).mock.calls[0];
    expect(title).toMatch(/blocked/i);
    expect(options.description).toMatch(/site settings/i);
  });

  it('shows unsupported message when not supported', async () => {
    (isPushSupported as any).mockReturnValue(false);
    (getPushState as any).mockResolvedValue(false);
    render(<PushNotificationPreference />);
    expect(await screen.findByText(/does not support push notifications/i)).toBeInTheDocument();
  });
});

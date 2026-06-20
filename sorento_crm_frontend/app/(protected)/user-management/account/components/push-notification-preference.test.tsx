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
    (subscribeToPush as any).mockResolvedValue(true);
    render(<PushNotificationPreference />);
    const btn = await screen.findByRole('button', { name: /enable notifications/i });
    fireEvent.click(btn);
    await waitFor(() => expect(subscribeToPush).toHaveBeenCalled());
  });

  it('shows unsupported message when not supported', async () => {
    (isPushSupported as any).mockReturnValue(false);
    (getPushState as any).mockResolvedValue(false);
    render(<PushNotificationPreference />);
    expect(await screen.findByText(/does not support push notifications/i)).toBeInTheDocument();
  });
});

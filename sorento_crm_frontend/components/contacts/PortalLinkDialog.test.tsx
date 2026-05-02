import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PortalLinkDialog from './PortalLinkDialog';

vi.mock('@/services/contactPortalLinkService', () => ({
  getContactPortalLink: vi.fn(),
  sendContactPortalLink: vi.fn(),
}));

import {
  getContactPortalLink,
  sendContactPortalLink,
} from '@/services/contactPortalLinkService';

function renderDialog(props: Partial<React.ComponentProps<typeof PortalLinkDialog>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PortalLinkDialog
        open
        onOpenChange={() => {}}
        contactId="c1"
        contactLabel="Tester"
        canSendViaRespondIo
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe('PortalLinkDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it('renders portal URL and expiry on success', async () => {
    (getContactPortalLink as any).mockResolvedValue({
      token: 'tok123',
      portal_url: 'https://crm.example.com/portal?token=tok123',
      expires_at: '2026-05-08T12:00:00Z',
      reused: false,
    });
    renderDialog();
    await waitFor(() =>
      expect(
        screen.getByDisplayValue('https://crm.example.com/portal?token=tok123'),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/Expires/i)).toBeInTheDocument();
    expect(screen.queryByText(/Reused existing link/i)).not.toBeInTheDocument();
  });

  it('shows reused badge when reused=true', async () => {
    (getContactPortalLink as any).mockResolvedValue({
      token: 'tok',
      portal_url: 'https://x/portal?token=tok',
      expires_at: '2026-05-08T12:00:00Z',
      reused: true,
    });
    renderDialog();
    await waitFor(() => screen.getByText(/Reused existing link/i));
  });

  it('copies link to clipboard on Copy click', async () => {
    (getContactPortalLink as any).mockResolvedValue({
      token: 'tok',
      portal_url: 'https://x/portal?token=tok',
      expires_at: '2026-05-08T12:00:00Z',
      reused: false,
    });
    renderDialog();
    await waitFor(() => screen.getByDisplayValue('https://x/portal?token=tok'));
    fireEvent.click(screen.getByRole('button', { name: /copy/i }));
    await waitFor(() =>
      expect((navigator.clipboard.writeText as any)).toHaveBeenCalledWith(
        'https://x/portal?token=tok',
      ),
    );
  });

  it('fires send mutation on Send via Respond.io click', async () => {
    (getContactPortalLink as any).mockResolvedValue({
      token: 'tok',
      portal_url: 'https://x/portal?token=tok',
      expires_at: '2026-05-08T12:00:00Z',
      reused: false,
    });
    (sendContactPortalLink as any).mockResolvedValue({
      token: 'tok',
      portal_url: 'https://x/portal?token=tok',
      expires_at: '2026-05-08T12:00:00Z',
      reused: true,
      sent: true,
    });
    renderDialog();
    await waitFor(() => screen.getByDisplayValue('https://x/portal?token=tok'));
    fireEvent.click(screen.getByRole('button', { name: /send via respond\.io/i }));
    await waitFor(() => expect(sendContactPortalLink).toHaveBeenCalled());
    expect((sendContactPortalLink as any).mock.calls[0][0]).toBe('c1');
  });

  it('disables Send when canSendViaRespondIo is false', async () => {
    (getContactPortalLink as any).mockResolvedValue({
      token: 'tok',
      portal_url: 'https://x/portal?token=tok',
      expires_at: '2026-05-08T12:00:00Z',
      reused: false,
    });
    renderDialog({ canSendViaRespondIo: false });
    await waitFor(() => screen.getByDisplayValue('https://x/portal?token=tok'));
    expect(screen.getByRole('button', { name: /send via respond\.io/i })).toBeDisabled();
  });
});

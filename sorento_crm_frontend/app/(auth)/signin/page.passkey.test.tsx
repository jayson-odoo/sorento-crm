/**
 * PASSKEY-LOGIN AC-40 / AC-41 on the /signin page itself (the button alone is
 * covered by components/passkey-signin-button.test.tsx):
 *   - the round "Passkey" button sits beside "Phone number" under the
 *     "or Log in with" divider, and a passkey sign-in lands where a password
 *     sign-in lands; a refusal shows in the page's error Alert;
 *   - the Email input carries `autocomplete="username webauthn"`, and where
 *     conditional mediation is available the page starts an autofill passkey
 *     request on mount.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '@/components/ui/tooltip';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('next-auth/react', () => ({
  signIn: vi.fn(),
  getSession: vi.fn(),
}));

vi.mock('@/services/phoneSigninService', () => ({
  requestSigninCode: vi.fn(),
}));

const webauthn = vi.hoisted(() => ({
  startAuthentication: vi.fn(),
  startRegistration: vi.fn(),
  browserSupportsWebAuthnAutofill: vi.fn(async () => false),
}));
vi.mock('@simplewebauthn/browser', () => webauthn, { virtual: true });

const svc = vi.hoisted(() => ({
  fetchPasskeyStatus: vi.fn(),
  fetchPasskeySignInOptions: vi.fn(),
  fetchMyPasskeys: vi.fn(),
  sendPasskeyReauthCode: vi.fn(),
  fetchPasskeyRegistrationOptions: vi.fn(),
  registerPasskey: vi.fn(),
  renamePasskey: vi.fn(),
  fetchUserPasskeys: vi.fn(),
  setUserPasskeyEnabled: vi.fn(),
}));
vi.mock('@/services/passkeyService', () => svc);

import Page from './page';
import { getSession, signIn } from 'next-auth/react';

const mockSignIn = vi.mocked(signIn);
const mockGetSession = vi.mocked(getSession);

const OPTIONS = { challenge: 'Y2hhbGxlbmdl', rpId: 'localhost', userVerification: 'required' };
const CREDENTIAL = { id: 'cred-1', rawId: 'cred-1', type: 'public-key', response: {} };

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
  );
}

function setWebAuthn({ conditional }: { conditional: boolean }) {
  const PKC = function PublicKeyCredential() {} as unknown as Record<string, unknown>;
  if (conditional) PKC.isConditionalMediationAvailable = vi.fn(async () => true);
  Object.defineProperty(window, 'PublicKeyCredential', {
    value: PKC,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
}

beforeEach(() => {
  vi.clearAllMocks();
  setWebAuthn({ conditional: false });
  webauthn.browserSupportsWebAuthnAutofill.mockResolvedValue(false);
  svc.fetchPasskeyStatus.mockResolvedValue({ enabled: true });
  svc.fetchPasskeySignInOptions.mockResolvedValue({ challenge_id: 'ch-1', options: OPTIONS });
  webauthn.startAuthentication.mockResolvedValue(CREDENTIAL);
  mockSignIn.mockResolvedValue({ ok: true, error: null, status: 200, url: null } as never);
  mockGetSession.mockResolvedValue({ user: { homePath: '/dashboard' } } as never);
});

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).PublicKeyCredential;
});

describe('/signin passkey button (AC-40)', () => {
  it('shows a round "Passkey" button after the "Phone number" one, under the divider', async () => {
    render(<Page />, { wrapper });
    const passkey = await screen.findByRole('button', { name: 'Passkey' });
    const phone = screen.getByRole('button', { name: 'Phone number' });
    const divider = screen.getByText('or Log in with');
    const FOLLOWING = Node.DOCUMENT_POSITION_FOLLOWING;
    expect(divider.compareDocumentPosition(passkey) & FOLLOWING).toBeTruthy();
    expect(phone.compareDocumentPosition(passkey) & FOLLOWING).toBeTruthy();
    expect(passkey.className).toContain('rounded-full');
  });

  it('lands where a password sign-in lands after a passkey sign-in', async () => {
    render(<Page />, { wrapper });
    fireEvent.click(await screen.findByRole('button', { name: 'Passkey' }));

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/dashboard'));
    expect(mockSignIn).toHaveBeenCalledWith(
      'passkey',
      expect.objectContaining({ redirect: false, challengeId: 'ch-1' }),
    );
  });

  it("shows the backend's refusal in the page's error Alert", async () => {
    mockSignIn.mockResolvedValue({
      ok: false,
      status: 401,
      url: null,
      error: JSON.stringify({ code: 401, message: "That passkey didn't work. Sign in another way." }),
    } as never);
    render(<Page />, { wrapper });
    fireEvent.click(await screen.findByRole('button', { name: 'Passkey' }));

    expect(
      await screen.findByText("That passkey didn't work. Sign in another way."),
    ).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });
});

describe('/signin passkey autofill (AC-41)', () => {
  it('the Email input has autocomplete="username webauthn"', () => {
    render(<Page />, { wrapper });
    expect(screen.getByPlaceholderText('Your email')).toHaveAttribute(
      'autocomplete',
      'username webauthn',
    );
  });

  it('starts a conditional (autofill) passkey request on mount where available', async () => {
    setWebAuthn({ conditional: true });
    webauthn.browserSupportsWebAuthnAutofill.mockResolvedValue(true);
    // The autofill request stays open until the user picks a passkey.
    webauthn.startAuthentication.mockReturnValue(new Promise(() => {}));
    render(<Page />, { wrapper });

    await waitFor(() =>
      expect(webauthn.startAuthentication).toHaveBeenCalledWith(
        expect.objectContaining({ optionsJSON: OPTIONS, useBrowserAutofill: true }),
      ),
    );
  });

  it('starts no autofill request where conditional mediation is unavailable', async () => {
    render(<Page />, { wrapper });
    await screen.findByRole('button', { name: 'Passkey' });
    await new Promise((r) => setTimeout(r, 20));
    expect(webauthn.startAuthentication).not.toHaveBeenCalled();
  });
});

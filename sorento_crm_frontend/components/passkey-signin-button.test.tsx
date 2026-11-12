/**
 * PASSKEY-LOGIN AC-40: the round "Passkey" button on /signin.
 *
 * Shown only when the browser can do WebAuthn (`window.PublicKeyCredential`),
 * the page is a secure context, and `/auth/passkey/status` says enabled.
 * Click: options -> `startAuthentication({ optionsJSON })` -> NextAuth
 * `signIn('passkey', { redirect: false, challengeId, credential: JSON })` ->
 * `onSignedIn`. A cancelled browser prompt (NotAllowedError) shows nothing;
 * a backend refusal reaches `onError` as the backend's message.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const webauthn = vi.hoisted(() => ({
  startAuthentication: vi.fn(),
  startRegistration: vi.fn(),
  browserSupportsWebAuthnAutofill: vi.fn(async () => false),
}));
// Not installed until the implementation lands; the test never imports it
// directly, so a red run fails on the missing product module, not on this.
vi.mock('@simplewebauthn/browser', () => webauthn, { virtual: true });

vi.mock('next-auth/react', () => ({
  signIn: vi.fn(),
  getSession: vi.fn(),
}));

vi.mock('@/services/passkeyService', () => ({
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

import { signIn } from 'next-auth/react';
import { fetchPasskeySignInOptions, fetchPasskeyStatus } from '@/services/passkeyService';
import PasskeySignInButton from './passkey-signin-button';

const mockStart = webauthn.startAuthentication;
const mockSignIn = vi.mocked(signIn);
const mockStatus = vi.mocked(fetchPasskeyStatus);
const mockOptions = vi.mocked(fetchPasskeySignInOptions);

const OPTIONS = { challenge: 'Y2hhbGxlbmdl', rpId: 'localhost', userVerification: 'required' };
const CREDENTIAL = {
  id: 'cred-1',
  rawId: 'cred-1',
  type: 'public-key',
  response: { clientDataJSON: 'a', authenticatorData: 'b', signature: 'c' },
  clientExtensionResults: {},
};

function setSecure(value: boolean) {
  Object.defineProperty(window, 'isSecureContext', { value, configurable: true });
}

function setWebAuthn(present: boolean) {
  if (present) {
    // No isConditionalMediationAvailable here: autofill is the page's concern
    // (AC-41, page.passkey.test.tsx); this file is about the button alone.
    Object.defineProperty(window, 'PublicKeyCredential', {
      value: function PublicKeyCredential() {},
      configurable: true,
      writable: true,
    });
  } else {
    delete (window as unknown as Record<string, unknown>).PublicKeyCredential;
  }
}

function renderButton(props: Partial<{ onSignedIn: () => void; onError: (m: string) => void; disabled: boolean }> = {}) {
  const onSignedIn = props.onSignedIn ?? vi.fn();
  const onError = props.onError ?? vi.fn();
  render(<PasskeySignInButton onSignedIn={onSignedIn} onError={onError} disabled={props.disabled} />);
  return { onSignedIn, onError };
}

beforeEach(() => {
  vi.clearAllMocks();
  setWebAuthn(true);
  setSecure(true);
  mockStatus.mockResolvedValue({ enabled: true } as never);
  mockOptions.mockResolvedValue({ challenge_id: 'ch-1', options: OPTIONS } as never);
  mockStart.mockResolvedValue(CREDENTIAL as never);
  mockSignIn.mockResolvedValue({ ok: true, error: null, status: 200, url: null } as never);
});

afterEach(() => {
  setWebAuthn(false);
});

describe('PasskeySignInButton - when it shows (AC-40)', () => {
  it('shows a "Passkey" button when supported, secure and enabled', async () => {
    renderButton();
    expect(await screen.findByRole('button', { name: 'Passkey' })).toBeInTheDocument();
  });

  it('shows nothing when the browser has no PublicKeyCredential', async () => {
    setWebAuthn(false);
    renderButton();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole('button', { name: 'Passkey' })).not.toBeInTheDocument();
  });

  it('shows nothing on an insecure address', async () => {
    setSecure(false);
    renderButton();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole('button', { name: 'Passkey' })).not.toBeInTheDocument();
  });

  it('shows nothing when the backend says passkeys are not enabled', async () => {
    mockStatus.mockResolvedValue({ enabled: false } as never);
    renderButton();
    await waitFor(() => expect(mockStatus).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole('button', { name: 'Passkey' })).not.toBeInTheDocument();
  });

  it('is disabled while the page is busy', async () => {
    renderButton({ disabled: true });
    expect(await screen.findByRole('button', { name: 'Passkey' })).toBeDisabled();
  });
});

describe('PasskeySignInButton - signing in (AC-40)', () => {
  it('runs options -> startAuthentication -> signIn("passkey") -> onSignedIn', async () => {
    const { onSignedIn, onError } = renderButton();
    fireEvent.click(await screen.findByRole('button', { name: 'Passkey' }));

    await waitFor(() => expect(onSignedIn).toHaveBeenCalledTimes(1));
    expect(mockOptions).toHaveBeenCalledTimes(1);
    expect(mockStart).toHaveBeenCalledWith(expect.objectContaining({ optionsJSON: OPTIONS }));
    expect(mockSignIn).toHaveBeenCalledWith('passkey', {
      redirect: false,
      challengeId: 'ch-1',
      credential: JSON.stringify(CREDENTIAL),
    });
    expect(onError).not.toHaveBeenCalled();
  });

  it('shows no error when the user cancels the browser prompt', async () => {
    const cancelled = Object.assign(new Error('The operation either timed out or was not allowed.'), {
      name: 'NotAllowedError',
    });
    mockStart.mockRejectedValue(cancelled);
    const { onSignedIn, onError } = renderButton();
    fireEvent.click(await screen.findByRole('button', { name: 'Passkey' }));

    await waitFor(() => expect(mockStart).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(onError).not.toHaveBeenCalled();
    expect(onSignedIn).not.toHaveBeenCalled();
    expect(mockSignIn).not.toHaveBeenCalled();
  });

  it('hands the backend refusal message to onError', async () => {
    mockSignIn.mockResolvedValue({
      ok: false,
      status: 401,
      url: null,
      error: JSON.stringify({ code: 401, message: "That passkey didn't work. Sign in another way." }),
    } as never);
    const { onSignedIn, onError } = renderButton();
    fireEvent.click(await screen.findByRole('button', { name: 'Passkey' }));

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("That passkey didn't work. Sign in another way."),
    );
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it('hands an options-stage refusal (rate limit) to onError', async () => {
    mockOptions.mockRejectedValue(new Error('Too many attempts. Try again in a minute.'));
    const { onError } = renderButton();
    fireEvent.click(await screen.findByRole('button', { name: 'Passkey' }));

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith('Too many attempts. Try again in a minute.'),
    );
    expect(mockStart).not.toHaveBeenCalled();
  });
});

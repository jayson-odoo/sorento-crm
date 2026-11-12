/**
 * PASSKEY-LOGIN AC-43 / AC-44 / AC-46: the "Passkeys" Card on My account >
 * Security.
 *
 * Mocked at the SERVICE boundary (not the hooks), so the real
 * `hooks/usePasskeys.ts` and the card are exercised together and a toast
 * fires wherever the layering puts it.
 *
 * Whether the user has a password is read from the account context (the page
 * reads `has_password ?? hasPassword` the same way); the card is also handed
 * `hasPassword` as a prop in case it takes it that way.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { User } from '@/app/models/user';

const webauthn = vi.hoisted(() => ({
  startAuthentication: vi.fn(),
  startRegistration: vi.fn(),
  browserSupportsWebAuthnAutofill: vi.fn(async () => false),
  WebAuthnAbortService: { cancelCeremony: vi.fn() },
}));
// Not installed until the implementation lands; the test never imports it
// directly, so a red run fails on the missing product module, not on this.
vi.mock('@simplewebauthn/browser', () => webauthn, { virtual: true });

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

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

const deferredActionInput = vi.fn();
const removeStart = vi.fn();
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (input: unknown) => {
    deferredActionInput(input);
    return {
      pending: null,
      isPending: false,
      isBlocked: false,
      start: removeStart,
      cancel: vi.fn(),
      countdown: null,
    };
  },
}));

import { AccountProvider } from '../../components/account-context';
import PasskeysCardImpl from './passkeys-card';

const PasskeysCard = PasskeysCardImpl as unknown as React.ComponentType<Record<string, unknown>>;
const mockStartRegistration = webauthn.startRegistration;

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

const PK_IPHONE = {
  id: 'a1111111-1111-4111-8111-111111111111',
  name: 'Safari on iPhone',
  created_at: '2026-11-12T09:42:00',
  last_used_at: '2026-11-12T09:42:00',
};
const PK_MAC = {
  id: 'b2222222-2222-4222-8222-222222222222',
  name: 'Office Mac',
  created_at: '2026-11-03T01:00:00',
  last_used_at: null,
};
const REG_OPTIONS = { challenge: 'cmVn', rp: { id: 'localhost', name: 'Sorento CRM' } };
const REG_CREDENTIAL = { id: 'new-cred', rawId: 'new-cred', type: 'public-key', response: {} };

function accountUser(hasPassword: boolean): User {
  return {
    id: 'me-1',
    email: 'me@example.test',
    name: 'Me',
    hasPassword,
    has_password: hasPassword,
    passkeyEnabled: true,
    passkey_enabled: true,
  } as unknown as User;
}

function setSupport({ hasWebAuthn = true, secure = true } = {}) {
  Object.defineProperty(window, 'isSecureContext', { value: secure, configurable: true });
  if (hasWebAuthn) {
    Object.defineProperty(window, 'PublicKeyCredential', {
      value: function PublicKeyCredential() {},
      configurable: true,
      writable: true,
    });
  } else {
    delete (window as unknown as Record<string, unknown>).PublicKeyCredential;
  }
}

function renderCard({ hasPassword = true } = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <AccountProvider user={accountUser(hasPassword)}>
        <PasskeysCard hasPassword={hasPassword} />
      </AccountProvider>
    </QueryClientProvider>,
  );
}

async function openRowMenu(index: number) {
  await screen.findByText(PK_IPHONE.name);
  const triggers = document.querySelectorAll<HTMLElement>('[aria-haspopup="menu"]');
  const trigger = triggers[index];
  expect(trigger).toBeTruthy();
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  if (trigger.getAttribute('aria-expanded') !== 'true') fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
}

async function openAddDialog() {
  const add = await screen.findByRole('button', { name: 'Add passkey' });
  await waitFor(() => expect(add).toBeEnabled());
  fireEvent.click(add);
  return screen.findByRole('dialog', { name: "Confirm it's you" });
}

beforeEach(() => {
  vi.clearAllMocks();
  setSupport();
  svc.fetchPasskeyStatus.mockResolvedValue({ enabled: true });
  svc.fetchMyPasskeys.mockResolvedValue([PK_IPHONE, PK_MAC]);
  svc.fetchPasskeyRegistrationOptions.mockResolvedValue({
    challenge_id: 'reg-1',
    options: REG_OPTIONS,
  });
  svc.sendPasskeyReauthCode.mockResolvedValue({
    sent_to: '+60•••6789',
    expires_in_seconds: 600,
    resend_in_seconds: 60,
  });
  svc.registerPasskey.mockResolvedValue({
    id: 'c3333333-3333-4333-8333-333333333333',
    name: 'Chrome on Linux',
    created_at: '2026-11-12T10:00:00',
    last_used_at: null,
  });
  svc.renamePasskey.mockResolvedValue({ ...PK_IPHONE, name: 'Work phone' });
  mockStartRegistration.mockResolvedValue(REG_CREDENTIAL as never);
});

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).PublicKeyCredential;
});

describe('PasskeysCard - list (AC-43)', () => {
  it('has the "Passkeys" title and an enabled "Add passkey" button', async () => {
    renderCard();
    expect(screen.getByText('Passkeys')).toBeInTheDocument();
    const add = await screen.findByRole('button', { name: 'Add passkey' });
    await waitFor(() => expect(add).toBeEnabled());
  });

  it('lists each passkey with its name, added date and last use', async () => {
    renderCard();
    const name = await screen.findByText('Safari on iPhone');
    expect(name).toHaveAttribute('title', 'Safari on iPhone');
    expect(screen.getByText('Office Mac')).toBeInTheDocument();
    expect(screen.getByText('Added 12/11/2026')).toBeInTheDocument();
    expect(screen.getByText('Added 03/11/2026')).toBeInTheDocument();
    expect(screen.getByText(/^Last used 12\/11\/2026, 5:42[\s\u202f]pm$/)).toBeInTheDocument();
    expect(screen.getByText('Never used')).toBeInTheDocument();
  });

  it('never shows a passkey id', async () => {
    renderCard();
    await screen.findByText('Safari on iPhone');
    expect(document.body.textContent ?? '').not.toMatch(UUID_RE);
  });

  it('shows the empty state with no second button', async () => {
    svc.fetchMyPasskeys.mockResolvedValue([]);
    renderCard();
    expect(await screen.findByText('No passkeys yet')).toBeInTheDocument();
    expect(
      screen.getByText('Sign in with Face ID, Touch ID or your fingerprint.'),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /add passkey/i })).toHaveLength(1);
  });
});

describe('PasskeysCard - failed list load (AC-47)', () => {
  it('shows the shared ListLoadFailure with a retry that refetches, never a dead end', async () => {
    svc.fetchMyPasskeys.mockRejectedValue(new Error('Failed to load passkeys'));
    renderCard();

    const failure = await screen.findByTestId('data-grid-error');
    expect(within(failure).getByRole('alert')).toHaveTextContent('Failed to load passkeys');
    expect(screen.queryByText('No passkeys yet')).not.toBeInTheDocument();

    const callsBefore = svc.fetchMyPasskeys.mock.calls.length;
    svc.fetchMyPasskeys.mockResolvedValue([PK_IPHONE]);
    // UAC says "Try again"; the shared ListLoadFailure labels it "Retry". Either passes.
    fireEvent.click(within(failure).getByRole('button', { name: /^(try again|retry)$/i }));

    await waitFor(() =>
      expect(svc.fetchMyPasskeys.mock.calls.length).toBeGreaterThan(callsBefore),
    );
    expect(await screen.findByText('Safari on iPhone')).toBeInTheDocument();
  });
});

describe('PasskeysCard - unsupported (AC-43)', () => {
  it.each([
    ['a browser without WebAuthn', () => setSupport({ hasWebAuthn: false })],
    ['an insecure address', () => setSupport({ secure: false })],
    ['passkeys disabled on the server', () => svc.fetchPasskeyStatus.mockResolvedValue({ enabled: false })],
  ])('disables "Add passkey" with the hint on %s', async (_label, arrange) => {
    arrange();
    renderCard();
    expect(await screen.findByText("This browser can't use passkeys.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add passkey' })).toBeDisabled();
  });
});

describe('PasskeysCard - add (AC-44)', () => {
  it('confirms with the password, then registers and toasts "Passkey added"', async () => {
    renderCard({ hasPassword: true });
    const dialog = await openAddDialog();

    fireEvent.change(within(dialog).getByLabelText('Password'), {
      target: { value: 'hunter22' },
    });
    const listCallsBefore = svc.fetchMyPasskeys.mock.calls.length;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Continue' }));

    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Passkey added'));
    expect(svc.fetchPasskeyRegistrationOptions).toHaveBeenCalledWith({ password: 'hunter22' });
    expect(mockStartRegistration).toHaveBeenCalledWith(
      expect.objectContaining({ optionsJSON: REG_OPTIONS }),
    );
    expect(svc.registerPasskey.mock.calls[0][0]).toBe('reg-1');
    expect(svc.registerPasskey.mock.calls[0][1]).toEqual(REG_CREDENTIAL);
    await waitFor(() =>
      expect(svc.fetchMyPasskeys.mock.calls.length).toBeGreaterThan(listCallsBefore),
    );
  });

  it('asks a user without a password for a phone code instead', async () => {
    renderCard({ hasPassword: false });
    const dialog = await openAddDialog();

    expect(within(dialog).queryByLabelText('Password')).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send code' }));
    await waitFor(() => expect(svc.sendPasskeyReauthCode).toHaveBeenCalledTimes(1));

    fireEvent.change(within(dialog).getByPlaceholderText('6-digit code'), {
      target: { value: '123456' },
    });
    // The shared code field may auto-submit at six digits; press Continue only if it did not.
    await new Promise((r) => setTimeout(r, 20));
    if (svc.fetchPasskeyRegistrationOptions.mock.calls.length === 0) {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Continue' }));
    }

    await waitFor(() =>
      expect(svc.fetchPasskeyRegistrationOptions).toHaveBeenCalledWith({ phone_code: '123456' }),
    );
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Passkey added'));
  });

  it('offers "Use a phone code instead" to a user who has a password', async () => {
    renderCard({ hasPassword: true });
    const dialog = await openAddDialog();

    fireEvent.click(within(dialog).getByText('Use a phone code instead'));
    expect(await within(dialog).findByRole('button', { name: 'Send code' })).toBeInTheDocument();
  });

  it('does nothing when the user cancels the browser prompt', async () => {
    mockStartRegistration.mockRejectedValue(
      Object.assign(new Error('not allowed'), { name: 'NotAllowedError' }),
    );
    renderCard({ hasPassword: true });
    const dialog = await openAddDialog();
    fireEvent.change(within(dialog).getByLabelText('Password'), {
      target: { value: 'hunter22' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Continue' }));

    await waitFor(() => expect(mockStartRegistration).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(svc.registerPasskey).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('shows the backend message for a wrong password and registers nothing', async () => {
    svc.fetchPasskeyRegistrationOptions.mockRejectedValue(
      new Error('That password is not right.'),
    );
    renderCard({ hasPassword: true });
    const dialog = await openAddDialog();
    fireEvent.change(within(dialog).getByLabelText('Password'), {
      target: { value: 'wrong' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Continue' }));

    await waitFor(() => {
      const shownInline = screen.queryByText('That password is not right.') !== null;
      const toasted = toastError.mock.calls.some((c) => c[0] === 'That password is not right.');
      expect(shownInline || toasted).toBe(true);
    });
    expect(mockStartRegistration).not.toHaveBeenCalled();
    expect(svc.registerPasskey).not.toHaveBeenCalled();
  });
});

describe('PasskeysCard - rename and remove (AC-44)', () => {
  it('renames from the row menu; Save is disabled for a blank name', async () => {
    renderCard();
    await openRowMenu(0);
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }));

    const dialog = await screen.findByRole('dialog');
    const input = within(dialog).getByRole('textbox');
    expect(input).toHaveValue('Safari on iPhone');

    fireEvent.change(input, { target: { value: '   ' } });
    expect(within(dialog).getByRole('button', { name: 'Save' })).toBeDisabled();

    fireEvent.change(input, { target: { value: 'Work phone' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(svc.renamePasskey).toHaveBeenCalledWith(PK_IPHONE.id, 'Work phone'),
    );
  });

  it('removes through the deferred action, with no confirm dialog', async () => {
    renderCard();
    await screen.findByText('Safari on iPhone');
    expect(deferredActionInput).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'user_passkey.delete',
        entityType: 'user_passkey',
        entityId: PK_IPHONE.id,
      }),
    );

    await openRowMenu(0);
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove' }));

    await waitFor(() => expect(removeStart).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });
});

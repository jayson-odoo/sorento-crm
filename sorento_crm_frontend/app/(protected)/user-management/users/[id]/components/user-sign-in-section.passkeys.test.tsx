/**
 * PASSKEY-LOGIN AC-45 (+ AC-32 word, AC-46 no UUIDs): the admin user detail
 * Sign-in card gains
 *   - "Passkey sign-in": the shared Switch for a viewer with
 *     `user_management.users.edit` (toast "Passkey sign-in turned on/off"),
 *     plain "On"/"Off" text otherwise;
 *   - "Passkeys": "N passkey(s)" opening a Dialog of that user's passkeys (row
 *     menu with Remove only with `users.edit`), or "None";
 *   - `lastSignInMethod: 'passkey'` reads ", passkey".
 *
 * Assumed User fields (camelCase mapping in app/models/user.ts):
 * `passkeyEnabled` and `passkeyCount`. Fixtures also carry the list through
 * `fetchUserPasskeys`, so a count read from the list works the same.
 *
 * Mocked at the service boundary so the real `hooks/usePasskeys.ts` runs.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { User } from '@/app/models/user';
import { UserStatus } from '@/app/models/user';

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

const canEditRef = vi.hoisted(() => ({ current: true }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => canEditRef.current,
}));

const deferredActionInput = vi.fn();
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (input: unknown) => {
    deferredActionInput(input);
    return {
      pending: null,
      isPending: false,
      isBlocked: false,
      start: vi.fn(),
      cancel: vi.fn(),
      countdown: null,
    };
  },
}));

vi.mock('../../actions', () => ({
  useUserActions: () => ({ resendInviteAction: null, dialogs: null }),
}));

vi.mock('../../services/userService', () => ({
  useNewNumber: vi.fn(),
}));

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

import UserSignInSection from './user-sign-in-section';

const USER_ID = 'e5555555-5555-4555-8555-555555555555';
const PASSKEYS = [
  {
    id: 'a1111111-1111-4111-8111-111111111111',
    name: 'Safari on iPhone',
    created_at: '2026-11-12T09:42:00',
    last_used_at: '2026-11-12T09:42:00',
  },
  {
    id: 'b2222222-2222-4222-8222-222222222222',
    name: 'Office Mac',
    created_at: '2026-11-03T01:00:00',
    last_used_at: null,
  },
];

function baseUser(over: Record<string, unknown> = {}): User {
  return {
    id: USER_ID,
    email: 'staff.one@example.test',
    name: 'Staff One',
    status: UserStatus.ACTIVE,
    isTrashed: false,
    isProtected: false,
    contactNumber: null,
    phoneVerifiedAt: null,
    linkedContact: null,
    phoneDiffersFromContact: false,
    lastSignInAt: null,
    lastSignInMethod: null,
    needsInvitation: false,
    passkeyEnabled: false,
    passkey_enabled: false,
    passkeyCount: 0,
    passkey_count: 0,
    ...over,
  } as unknown as User;
}

function enabledWith(count: number): Record<string, unknown> {
  return { passkeyEnabled: true, passkey_enabled: true, passkeyCount: count, passkey_count: count };
}

function renderSection(user: User) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <UserSignInSection user={user} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  canEditRef.current = true;
  svc.fetchUserPasskeys.mockResolvedValue(PASSKEYS);
  svc.setUserPasskeyEnabled.mockImplementation(async (userId: string, enabled: boolean) => ({
    user_id: userId,
    passkey_enabled: enabled,
  }));
});

afterEach(() => cleanup());

describe('UserSignInSection - "Passkey sign-in" row (AC-45)', () => {
  it('shows the row with a switch for a viewer with users.edit, off by default', () => {
    renderSection(baseUser());
    expect(screen.getByText('Passkey sign-in')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
  });

  it('turns passkey sign-in on through the service and toasts it', async () => {
    renderSection(baseUser());
    fireEvent.click(screen.getByRole('switch'));
    await waitFor(() => expect(svc.setUserPasskeyEnabled).toHaveBeenCalledWith(USER_ID, true));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Passkey sign-in turned on'));
  });

  it('turns passkey sign-in off through the service and toasts it', async () => {
    svc.fetchUserPasskeys.mockResolvedValue([]);
    renderSection(baseUser(enabledWith(0)));
    const sw = screen.getByRole('switch');
    expect(sw).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(sw);
    await waitFor(() => expect(svc.setUserPasskeyEnabled).toHaveBeenCalledWith(USER_ID, false));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Passkey sign-in turned off'));
  });

  it('reads "Off" as plain text, with no switch, without users.edit', () => {
    canEditRef.current = false;
    renderSection(baseUser());
    expect(screen.getByText('Passkey sign-in')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.getByText('Off')).toBeInTheDocument();
  });

  it('reads "On" as plain text without users.edit when it is on', () => {
    canEditRef.current = false;
    svc.fetchUserPasskeys.mockResolvedValue([]);
    renderSection(baseUser(enabledWith(0)));
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.getByText('On')).toBeInTheDocument();
  });
});

describe('UserSignInSection - "Passkeys" row (AC-45)', () => {
  it('reads "None" when the user has no passkeys', async () => {
    svc.fetchUserPasskeys.mockResolvedValue([]);
    renderSection(baseUser(enabledWith(0)));
    expect(screen.getByText('Passkeys')).toBeInTheDocument();
    expect(await screen.findByText('None')).toBeInTheDocument();
  });

  it('reads "1 passkey" for one', async () => {
    svc.fetchUserPasskeys.mockResolvedValue([PASSKEYS[0]]);
    renderSection(baseUser(enabledWith(1)));
    expect(await screen.findByText('1 passkey')).toBeInTheDocument();
  });

  it('"2 passkeys" opens a dialog listing them, with Remove menus for users.edit', async () => {
    renderSection(baseUser(enabledWith(2)));
    fireEvent.click(await screen.findByText('2 passkeys'));

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Safari on iPhone')).toBeInTheDocument();
    expect(within(dialog).getByText('Office Mac')).toBeInTheDocument();
    expect(svc.fetchUserPasskeys).toHaveBeenCalledWith(USER_ID);
    expect(dialog.querySelectorAll('[aria-haspopup="menu"]').length).toBe(2);
    expect(deferredActionInput).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'user_passkey.delete',
        entityType: 'user_passkey',
        entityId: PASSKEYS[0].id,
      }),
    );
    expect(document.body.textContent ?? '').not.toMatch(UUID_RE);
  });

  it('lists passkeys with no row menu for a viewer without users.edit', async () => {
    canEditRef.current = false;
    renderSection(baseUser(enabledWith(2)));
    fireEvent.click(await screen.findByText('2 passkeys'));

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Safari on iPhone')).toBeInTheDocument();
    expect(dialog.querySelectorAll('[aria-haspopup="menu"]').length).toBe(0);
  });
});

describe('UserSignInSection - last sign-in by passkey (AC-32, AC-45)', () => {
  it('reads a passkey session as "passkey"', () => {
    renderSection(
      baseUser({ lastSignInAt: '2026-11-12T09:42:00Z', lastSignInMethod: 'passkey' }),
    );
    expect(screen.getByText(/, passkey$/)).toBeInTheDocument();
  });
});

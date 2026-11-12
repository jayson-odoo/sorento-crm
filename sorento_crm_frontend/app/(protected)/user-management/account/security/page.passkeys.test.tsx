/**
 * PASSKEY-LOGIN AC-43: My account > Security shows the Passkeys card ONLY when
 * the signed-in user's `passkey_enabled` (from `get_me`) is true, placed
 * between the Password card and the Delete Account card. Switch off = the page
 * exactly as before.
 *
 * The card itself is stubbed here; `components/passkeys-card.test.tsx` covers it.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { User } from '@/app/models/user';

const userRef = vi.hoisted(() => ({ current: null as unknown }));
vi.mock('../components/account-context', () => ({
  useAccount: () => ({ user: userRef.current }),
}));

vi.mock('./components/passkeys-card', () => ({
  default: () => <div data-testid="passkeys-card-stub">Passkeys card</div>,
}));

import Page from './page';

function user(passkeyEnabled: boolean): User {
  return {
    id: 'me-1',
    email: 'me@example.test',
    hasPassword: true,
    has_password: true,
    passkeyEnabled,
    passkey_enabled: passkeyEnabled,
  } as unknown as User;
}

function renderPage() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <Page />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  userRef.current = user(false);
});

describe('Security page - Passkeys card (AC-43)', () => {
  it('shows the card between Password and Delete Account when passkey sign-in is on', () => {
    userRef.current = user(true);
    renderPage();
    const card = screen.getByTestId('passkeys-card-stub');
    const password = screen.getByText('Password');
    const del = screen.getByText('Delete Account');
    expect(password.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(card.compareDocumentPosition(del) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows no Passkeys card when passkey sign-in is off', () => {
    userRef.current = user(false);
    renderPage();
    expect(screen.queryByTestId('passkeys-card-stub')).not.toBeInTheDocument();
    expect(screen.getByText('Password')).toBeInTheDocument();
    expect(screen.getByText('Delete Account')).toBeInTheDocument();
  });
});

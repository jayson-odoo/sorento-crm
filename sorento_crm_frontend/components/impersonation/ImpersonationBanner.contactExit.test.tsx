/**
 * PORTAL-P3-ROLE-MENU round 6, F4 (P3-26): Exit also ends the contact impersonation (best effort)
 * and clears the sessionStorage portal token only, then the existing stop and reload.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const stop = vi.fn();
vi.mock('@/hooks/useImpersonation', () => ({
  useImpersonation: () => ({
    session: {
      sessionId: 's1',
      startedAt: '2026-10-28T00:00:00Z',
      targetUser: { id: 'u1', name: 'Eric', email: 'e@x.test', avatar: null, role_name: 'salesperson' },
    },
    stop: (...a: unknown[]) => stop(...a),
    stopping: false,
  }),
}));
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));
const stopContact = vi.fn();
vi.mock('@/services/contactImpersonationService', () => ({
  stopContactImpersonation: (...a: unknown[]) => stopContact(...a),
}));

import { ImpersonationBanner } from './ImpersonationBanner';

const TOKEN_KEY = 'sorento.portalToken';
const SLUG_KEY = 'sorento.portalSlug';
const reload = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem(TOKEN_KEY, 'ADMIN-OWN-TOKEN');
  window.localStorage.setItem(SLUG_KEY, 'ADMINSLUG01');
  window.sessionStorage.setItem(TOKEN_KEY, 'IMP-TOKEN');
  stop.mockResolvedValue(undefined);
  vi.stubGlobal('location', { ...window.location, reload });
});

async function exit() {
  render(<ImpersonationBanner />);
  fireEvent.click(screen.getByTestId('impersonation-exit'));
  await waitFor(() => expect(reload).toHaveBeenCalled());
}

describe('ImpersonationBanner Exit ends the contact impersonation too (F4)', () => {
  it('stops the contact impersonation, clears only the session token, then stop + reload', async () => {
    stopContact.mockResolvedValue(undefined);
    await exit();
    expect(stopContact).toHaveBeenCalled();
    expect(stop).toHaveBeenCalled();
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
    expect(window.localStorage.getItem(SLUG_KEY)).toBe('ADMINSLUG01');
  });

  it('contact stop rejects: the exit is not blocked', async () => {
    stopContact.mockRejectedValue(new Error('network'));
    await exit();
    expect(stopContact).toHaveBeenCalled();
    expect(stop).toHaveBeenCalled();
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
  });
});

describe('ImpersonationBanner Exit of a plain staff view-as (T3)', () => {
  it('no impersonation portal token in this tab: contact stop is not called, stop and reload still happen', async () => {
    window.sessionStorage.clear();
    stopContact.mockResolvedValue(undefined);
    await exit();
    expect(stopContact).not.toHaveBeenCalled();
    expect(stop).toHaveBeenCalled();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
    expect(window.localStorage.getItem(SLUG_KEY)).toBe('ADMINSLUG01');
  });
});

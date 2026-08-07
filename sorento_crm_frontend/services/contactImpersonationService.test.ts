/**
 * Impersonation always opened port 3000.
 *
 * The backend builds the portal URL from `FRONTEND_BASE_URL`, one server-side value that
 * cannot be right for every reader. An admin working on any other host or port clicked
 * "Impersonate" and was thrown into a DIFFERENT running app - a stale build, or a login
 * screen, or another worktree entirely - while the token in the query string was perfectly
 * valid. The symptom reads as "impersonation is broken" and the cause is one env var.
 *
 * The token is what matters and it rides the query string, so only the origin is replaced.
 * The env value stays as it is: it also builds the links emailed and WhatsApped to real
 * contacts, and those must keep naming the deployed host.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { rebaseOnCurrentOrigin } from './contactImpersonationService';

const ORIGINAL = window.location.href;

function setOrigin(href: string) {
  // jsdom forbids assigning window.location, so replace the object outright.
  Object.defineProperty(window, 'location', {
    writable: true,
    value: new URL(href),
  });
}

beforeEach(() => setOrigin('http://localhost:3050/user-management/contacts'));
afterEach(() => setOrigin(ORIGINAL));

describe('rebaseOnCurrentOrigin', () => {
  it('moves a server-configured URL onto the port the admin is actually using', () => {
    expect(
      rebaseOnCurrentOrigin('http://localhost:3000/portal?token=abc123&impersonation=1'),
    ).toBe('http://localhost:3050/portal?token=abc123&impersonation=1');
  });

  it('keeps the token, which is the only part that carries identity', () => {
    const out = rebaseOnCurrentOrigin(
      'http://localhost:3000/portal?token=abc123&impersonation=1',
    );
    expect(out).toContain('token=abc123');
    expect(out).toContain('impersonation=1');
  });

  it('leaves a URL alone when it is already on this origin', () => {
    expect(rebaseOnCurrentOrigin('http://localhost:3050/portal?token=x')).toBe(
      'http://localhost:3050/portal?token=x',
    );
  });

  it('resolves a relative URL rather than mangling it', () => {
    // The backend falls back to a relative path when no base URL is configured at all.
    expect(rebaseOnCurrentOrigin('/portal?token=x')).toBe(
      'http://localhost:3050/portal?token=x',
    );
  });

  it('preserves a fragment', () => {
    expect(rebaseOnCurrentOrigin('http://localhost:3000/portal?token=x#step2')).toBe(
      'http://localhost:3050/portal?token=x#step2',
    );
  });

  it('returns garbage unchanged rather than throwing', () => {
    // A slightly wrong link beats a crash in a click handler: the caller only opens it in
    // response to a deliberate action, so the admin sees the failure and can report it.
    expect(rebaseOnCurrentOrigin('')).toBe('');
  });
});

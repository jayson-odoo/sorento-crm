/**
 * The debtor lookup tells the server which form is asking (PROJECT-REG-PORTAL audit round 3),
 * so `project_registration` is offered only its agent's own debtors; every other caller
 * sends no `kind` and keeps the unfiltered lookup.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { lookupDebtors } from './portal-client';

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const requestedUrl = () => String(vi.mocked(fetch).mock.calls.at(-1)?.[0]);

describe('lookupDebtors', () => {
  it('asks with kind=project_registration when the form passes it', async () => {
    await lookupDebtors('setia', 20, 'project_registration');
    const url = requestedUrl();
    expect(url).toContain('kind=project_registration');
    expect(url).toContain('q=setia');
  });

  it('sends no kind at all without one', async () => {
    await lookupDebtors('setia');
    expect(requestedUrl()).not.toContain('kind=');
  });
});

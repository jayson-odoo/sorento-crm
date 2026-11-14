/**
 * PROJECT-LEADS-REASSIGN, Phase 2 red tests: ReassignProjectDialog takes an optional
 * `initialUserId` so a row's "Reassign to <name>" opens it with that person preselected (UAC B5).
 *
 * The existing behaviour stays: a pending secondary-lead pick approves that request through
 * decide; anyone else is the plain owner update (PUT). Observed at `apiFetch`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-a', name: 'Sales A' },
    { id: 'u-b', name: 'Sales B' },
    { id: 'u-c', name: 'Sales C' },
  ]),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ id, value, onChange, options }: never) => (
    <select
      id={id}
      aria-label="Salesperson"
      value={value}
      onChange={(e) => (onChange as (v: string) => void)(e.target.value)}
    >
      <option value="" />
      {((options ?? []) as { value: string; label: string }[]).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

type Call = { url: string; method: string; body: unknown };
const calls: Call[] = [];
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiFetch: async (input: string, init: RequestInit = {}) => {
      const method = (init.method ?? 'GET').toUpperCase();
      calls.push({
        url: String(input),
        method,
        body: typeof init.body === 'string' ? JSON.parse(init.body) : null,
      });
      const ok = (b: unknown) =>
        new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
      if (method === 'GET' && String(input).includes('/takeover-requests')) {
        return ok({
          data: [
            {
              id: 'r-b',
              project_id: 'p1',
              kind: 'dispute',
              status: 'pending',
              requester_user_id: 'u-b',
              requester_name: 'Sales B',
              reason: 'Found it first.',
              created_at: '2026-10-20T02:00:00Z',
            },
          ],
        });
      }
      if (method === 'POST' && String(input).includes('/decide')) return ok({ id: 'r-b', status: 'approved' });
      if (method === 'PUT') return ok({ id: 'p1' });
      return ok({ data: [] });
    },
  };
});

import { ReassignProjectDialog } from './ReassignProjectDialog';

function project(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000142',
    title: 'Menara CONTOH',
    outcome: 'open',
    owner_user_id: 'u-c',
    owner_name: 'Sales C',
    primary_owner_user_id: 'u-a',
    primary_owner_name: 'Sales A',
    is_critical: false,
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    approval_state: null,
    ...over,
  } as Project;
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const select = () => screen.getByLabelText('Salesperson') as HTMLSelectElement;
const optionsLoaded = () =>
  waitFor(() => expect(select().querySelectorAll('option[value]:not([value=""])').length).toBeGreaterThan(1));
const puts = () => calls.filter((c) => c.method === 'PUT');
const decides = () => calls.filter((c) => c.method === 'POST' && c.url.includes('/decide'));

// The prop is new: typed loosely here so the red run fails on behaviour, not on tsc.
const Dialog = ReassignProjectDialog as unknown as React.ComponentType<{
  project: Project;
  onDone: () => void;
  initialUserId?: string;
}>;

beforeEach(() => {
  vi.clearAllMocks();
  calls.length = 0;
});

describe('ReassignProjectDialog initialUserId (B5)', () => {
  it('preselects the given person (the primary, not a pending lead) and submitting PUTs the owner', async () => {
    const onDone = vi.fn();
    wrap(<Dialog project={project()} onDone={onDone} initialUserId="u-a" />);
    await optionsLoaded();
    expect(select().value).toBe('u-a');
    const submit = screen.getByRole('button', { name: /^Reassign$/ });
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(puts()[0].body).toMatchObject({ owner_user_id: 'u-a' });
    expect(decides()).toHaveLength(0);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it('preselecting a pending secondary lead approves that request instead of the plain update', async () => {
    wrap(<Dialog project={project()} onDone={vi.fn()} initialUserId="u-b" />);
    await optionsLoaded();
    expect(select().value).toBe('u-b');
    fireEvent.click(screen.getByRole('button', { name: /^Reassign$/ }));
    await waitFor(() => expect(decides()).toHaveLength(1));
    expect(decides()[0].url).toContain('/takeover-requests/r-b/decide');
    expect(decides()[0].body).toMatchObject({ approve: true });
    expect(puts()).toHaveLength(0);
  });

  it('without initialUserId the current owner is selected and Reassign stays disabled (unchanged)', async () => {
    wrap(<Dialog project={project()} onDone={vi.fn()} />);
    await optionsLoaded();
    expect(select().value).toBe('u-c');
    expect(screen.getByRole('button', { name: /^Reassign$/ })).toBeDisabled();
  });
});

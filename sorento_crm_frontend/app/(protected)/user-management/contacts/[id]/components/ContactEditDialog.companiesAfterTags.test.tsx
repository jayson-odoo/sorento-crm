/**
 * TAG-UNION (crew pass on 6fca39fe): saving tags recomputes the contact's companies on the server.
 * The edit dialog must not then PUT the companies it loaded when it opened, or it overwrites the
 * recompute and leaves a fake own change. Companies are sent only when the user changed them in
 * this dialog, and before the tags (so the tag recompute keeps them as the person's own change).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.fn();
const setTags = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), custom: vi.fn() },
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { roleName: 'Super Admin' } }, status: 'authenticated' }),
}));
vi.mock('@/app/(protected)/system-management/companies/services/companyService', () => ({
  getCompaniesSelect: vi.fn().mockResolvedValue([
    { id: 'co-s', name: 'Sorento', code: 'S' },
    { id: 'co-m', name: 'Mocha', code: 'M' },
  ]),
}));
vi.mock('@/app/(protected)/system-management/respond-workspaces/services/respondWorkspaceService', () => ({
  listRespondWorkspaceSelect: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [] }),
}));
vi.mock('@/app/(protected)/user-management/contact-tags/hooks/useContactTags', () => ({
  useContactTagOptions: () => ({ data: [{ value: 't-m', label: 'TU Mocha' }] }),
  useSetContactTags: () => ({ mutateAsync: (...a: unknown[]) => setTags(...a) }),
}));
// Each multi-select becomes a row of "<placeholder>: add <label>" / "remove <label>" buttons.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value, onChange, options, placeholder,
  }: {
    value: string[]; onChange: (v: string[]) => void; options: { value: string; label: string }[]; placeholder?: string;
  }) =>
    React.createElement(
      'div',
      null,
      options.map((o) =>
        React.createElement(
          'button',
          {
            key: o.value,
            type: 'button',
            onClick: () => onChange(value.includes(o.value) ? value.filter((v) => v !== o.value) : [...value, o.value]),
          },
          `${placeholder}: ${value.includes(o.value) ? 'remove' : 'add'} ${o.label}`,
        ),
      ),
    ),
}));

import ContactEditDialog from './ContactEditDialog';

let client: QueryClient;
const calls: { url: string; method: string; body?: string }[] = [];

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  calls.length = 0;
  setTags.mockReset();
  setTags.mockImplementation(async () => {
    calls.push({ url: 'tags', method: 'PUT' });
    return [];
  });
  apiFetch.mockReset();
  apiFetch.mockImplementation(async (url: string, init?: { method?: string; body?: string }) => {
    calls.push({ url, method: init?.method ?? 'GET', body: init?.body });
    if (url.endsWith('/companies') && (init?.method ?? 'GET') === 'GET') {
      return { ok: true, json: async () => [{ id: 'co-s', name: 'Sorento', code: 'S' }] };
    }
    return { ok: true, json: async () => ({ id: 'c1' }) };
  });
});

function open() {
  const contact = { id: 'c1', phone_number: '+60123456789', name: 'Al', access_type_codes: [], tags: [] };
  render(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(ContactEditDialog, { open: true, closeDialog: vi.fn(), contact: contact as never }),
    ),
  );
}

const companyPuts = () => calls.filter((c) => c.url.endsWith('/companies') && c.method === 'PUT');

describe('ContactEditDialog companies vs live tag recompute', () => {
  it('a tag change with untouched companies sends no companies PUT', async () => {
    open();
    await screen.findByRole('button', { name: 'Select companies: remove Sorento' }); // loaded value applied
    fireEvent.click(screen.getByRole('button', { name: 'Select tags: add TU Mocha' }));
    fireEvent.click(screen.getByRole('button', { name: /update contact/i }));
    await waitFor(() => expect(setTags).toHaveBeenCalled());
    await waitFor(() => expect(client.isMutating()).toBe(0));
    expect(companyPuts()).toEqual([]);
  });

  it('companies changed in the dialog are sent, before the tags', async () => {
    open();
    await screen.findByRole('button', { name: 'Select companies: remove Sorento' }); // loaded value applied
    fireEvent.click(screen.getByRole('button', { name: 'Select companies: add Mocha' }));
    fireEvent.click(screen.getByRole('button', { name: 'Select tags: add TU Mocha' }));
    fireEvent.click(screen.getByRole('button', { name: /update contact/i }));
    await waitFor(() => expect(setTags).toHaveBeenCalled());
    await waitFor(() => expect(companyPuts()).toHaveLength(1));
    expect(JSON.parse(companyPuts()[0].body ?? '{}').company_ids.sort()).toEqual(['co-m', 'co-s']);
    const order = calls.filter((c) => c.method === 'PUT').map((c) => (c.url === 'tags' ? 'tags' : c.url.endsWith('/companies') ? 'companies' : 'contact'));
    expect(order.indexOf('companies')).toBeLessThan(order.indexOf('tags'));
  });
});

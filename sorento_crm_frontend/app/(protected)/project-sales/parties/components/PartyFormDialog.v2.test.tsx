/**
 * PROJECT-REGISTER-V2 B4: the create call answers 200 with an EXISTING party (201 for a new
 * one); the Parties page's create dialog then toasts "<name> already exists", not "added".
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '@/lib/toast';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));
let createStatus = 201;
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiFetch: async () =>
      new Response(
        JSON.stringify({ id: 'a1', name: 'Arkitek CONTOH', party_type: 'architect', is_active: true }),
        { status: createStatus, headers: { 'content-type': 'application/json' } },
      ),
  };
});
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ id, value, onChange, options }: never) => (
    <select id={id} value={value} onChange={(e) => (onChange as (v: string) => void)(e.target.value)}>
      {((options ?? []) as { value: string; label: string }[]).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { PartyFormDialog } from './PartyFormDialog';

function submit() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PartyFormDialog party={null} onDone={vi.fn()} />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: 'Arkitek CONTOH' } });
  fireEvent.submit(screen.getByLabelText(/^Name/).closest('form') as HTMLFormElement);
}

beforeEach(() => vi.clearAllMocks());

describe('B4 existing party on create', () => {
  it('a 200 answer toasts "<name> already exists" and never "added"', async () => {
    createStatus = 200;
    submit();
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith('Arkitek CONTOH already exists');
    expect(toast.success).not.toHaveBeenCalledWith('Arkitek CONTOH added');
  });

  it('a 201 answer still toasts "<name> added"', async () => {
    createStatus = 201;
    submit();
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Arkitek CONTOH added'));
  });
});

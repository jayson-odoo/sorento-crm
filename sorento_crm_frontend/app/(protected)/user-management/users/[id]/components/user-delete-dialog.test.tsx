/**
 * D2 - deleting a record from its own page returns to the list it came from.
 *
 * A record page cannot stay open on a row that no longer exists: the pager finds
 * nothing on its page and hides, and the reader is left on a dead URL. So the
 * delete's success hands control back to the caller, and the caller pushes the
 * href `BackToList` would have linked to - the list path WITH the page, sort,
 * search and filters the row click wrote into the detail URL.
 */
import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useBackToListHref } from '@/components/common/BackToList';
import UserDeleteDialog from './user-delete-dialog';
import type { User } from '@/app/models/user';

const push = vi.fn();
let search = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(search),
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

vi.mock('sonner', () => ({
  toast: { custom: vi.fn(), success: vi.fn(), error: vi.fn() },
}));

const user = {
  id: 'u-1',
  name: 'Ada Lovelace',
  email: 'ada@example.com',
} as User;

/** The record page's wiring: the same href Back points at, pushed on success. */
function Harness() {
  const backHref = useBackToListHref('/user-management/users');
  const router = { push };
  return (
    <UserDeleteDialog
      open
      closeDialog={() => {}}
      user={user}
      onSuccess={() => router.push(backHref)}
    />
  );
}

/**
 * The dialog only deletes once the email is confirmed. Submitting the form is
 * what the Delete button does; it is driven directly here because react-hook-form's
 * `formState` proxy does not re-render the disabled button under jsdom.
 */
function deleteTheUser() {
  const input = screen.getByPlaceholderText('Enter email address');
  fireEvent.change(input, { target: { value: user.email } });
  fireEvent.submit(input.closest('form')!);
}

beforeEach(() => {
  cleanup();
  push.mockReset();
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
  search = '';
});

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
}

describe('UserDeleteDialog', () => {
  it('D2: pushes the list path carrying the query string once the delete resolves', async () => {
    search = 'page=3&limit=25&sort=name&dir=asc&query=ada&roleId=r1';
    renderDialog();

    deleteTheUser();

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(
        '/user-management/users?page=3&limit=25&sort=name&dir=asc&query=ada&roleId=r1',
      ),
    );
    expect(apiFetch).toHaveBeenCalledWith('/api/user-management/users/u-1', {
      method: 'DELETE',
    });
  });

  it('D2: a record opened without list state returns to the bare list', async () => {
    renderDialog();

    deleteTheUser();

    await waitFor(() => expect(push).toHaveBeenCalledWith('/user-management/users'));
  });

  it('D2: a failed delete leaves the reader on the record', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      json: async () => ({ message: 'User is referenced by an order' }),
    });
    renderDialog();

    deleteTheUser();

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
  });
});

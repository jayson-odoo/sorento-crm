/**
 * Fix lane round 2 (reviewer Nit 4 on PR #1307): a save error shows once,
 * inline in the dialog (no second toast), and the dialog carries no
 * explanatory copy under its title.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    error: (...a: unknown[]) => toastError(...a),
    success: (...a: unknown[]) => toastSuccess(...a),
  },
}));

const setPassword = vi.fn();
vi.mock('@/services/accountPasswordService', () => ({
  setPassword: (...a: unknown[]) => setPassword(...a),
}));

import ChangePasswordDialog from './change-password-dialog';

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChangePasswordDialog open closeDialog={() => {}} hasPassword={false} />
    </QueryClientProvider>,
  );
}

describe('ChangePasswordDialog', () => {
  beforeEach(() => {
    toastError.mockReset();
    toastSuccess.mockReset();
    setPassword.mockReset();
  });

  it('has no explanatory description under the title', () => {
    renderDialog();
    expect(screen.queryByText('Manage your sign-in password')).toBeNull();
  });

  it('shows a save error once, inline, and not as a toast too', async () => {
    setPassword.mockRejectedValue(new Error('Password could not be saved.'));
    renderDialog();

    fireEvent.change(screen.getByPlaceholderText('Enter new password'), {
      target: { value: 'longenough1' },
    });
    fireEvent.change(screen.getByPlaceholderText('Re-enter new password'), {
      target: { value: 'longenough1' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() =>
      expect(screen.getByText('Password could not be saved.')).toBeTruthy(),
    );
    expect(screen.getAllByText('Password could not be saved.')).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });
});

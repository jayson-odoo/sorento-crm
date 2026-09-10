/**
 * `DescriptionEnCell` (S2, AC-E1-E3) - the shared Description (EN) cell the Packing tab
 * and the Lines tab both render.
 *
 * What this pins:
 * - Dash for a description the glossary has never seen; editable only when `canAdjust`
 *   and `description` is non-empty (AC-E1).
 * - Enter saves (PUT .../translations with {source_text, target_text}), Escape cancels
 *   with no request, blur saves only when the value actually changed (AC-E2).
 * - A failed save toasts the message `extractApiError` extracts from the response body.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/toast', () => ({ toast }));

import { DescriptionEnCell } from './DescriptionEnCell';

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    headers: { get: () => 'application/json' },
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

function renderCell(
  over: Partial<{ description: string | null; descriptionEn: string | null; canAdjust: boolean }> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <DescriptionEnCell
        invoiceId="pi-1"
        description={over.description ?? '连体马桶'}
        descriptionEn={over.descriptionEn ?? null}
        canAdjust={over.canAdjust ?? true}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiFetch.mockReset();
  toast.success.mockReset();
  toast.error.mockReset();
});

describe('DescriptionEnCell - dash / read states (AC-E1)', () => {
  it('shows a dash, editable, when the glossary has never seen this description', () => {
    renderCell({ descriptionEn: null });
    const dash = screen.getByRole('button', { name: 'Add English for 连体马桶' });
    expect(dash).toHaveTextContent('-');
  });

  it('renders a plain (non-clickable) dash when the caller cannot adjust the invoice', () => {
    renderCell({ descriptionEn: null, canAdjust: false });
    expect(screen.queryByRole('button', { name: /Add English/ })).not.toBeInTheDocument();
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('renders a plain dash when the row has no description to key on, even with canAdjust', () => {
    renderCell({ description: '', descriptionEn: null, canAdjust: true });
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('shows the English once the glossary knows it, as a clickable value', () => {
    renderCell({ descriptionEn: 'One-piece toilet' });
    expect(screen.getByRole('button', { name: 'One-piece toilet' })).toBeInTheDocument();
  });
});

describe('DescriptionEnCell - Enter saves (AC-E2)', () => {
  it('PUTs {source_text, target_text}, toasts the rebound count, and leaves edit mode', async () => {
    // `descriptionEn` itself is the PARENT's prop (the invoice/packing query re-fetching
    // after invalidation, exercised end to end by the Packing/Lines tab tests) - this
    // isolated render only proves the cell's own request + exit-edit-mode contract.
    apiFetch.mockResolvedValue(
      jsonResponse({
        source_text: '连体马桶',
        target_text: 'One-piece toilet',
        source: 'manual',
        rebound: { lines: 3, packing_rows: 1 },
      }),
    );
    renderCell({ descriptionEn: null });

    fireEvent.click(screen.getByRole('button', { name: 'Add English for 连体马桶' }));
    const input = screen.getByRole('textbox', { name: 'English for 连体马桶' });
    fireEvent.change(input, { target: { value: 'One-piece toilet' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/scm/proforma-invoices/pi-1/translations',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ source_text: '连体马桶', target_text: 'One-piece toilet' }),
      }),
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Translation saved, 4 rows updated'));
    // Back to the (still-null-prop) dash button, not the input - the save committed.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Add English for 连体马桶' })).toBeInTheDocument(),
    );
  });
});

describe('DescriptionEnCell - Escape cancels (AC-E2)', () => {
  it('reverts the value and sends no request', () => {
    renderCell({ descriptionEn: 'One-piece toilet' });

    fireEvent.click(screen.getByRole('button', { name: 'One-piece toilet' }));
    const input = screen.getByRole('textbox', { name: 'English for 连体马桶' });
    fireEvent.change(input, { target: { value: 'Wrong text' } });
    fireEvent.keyDown(input, { key: 'Escape' });

    expect(screen.getByRole('button', { name: 'One-piece toilet' })).toBeInTheDocument();
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

describe('DescriptionEnCell - blur saves only if changed (AC-E2)', () => {
  it('saves on blur when the value changed', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({
        source_text: '连体马桶',
        target_text: 'One-piece toilet',
        source: 'manual',
        rebound: { lines: 0, packing_rows: 0 },
      }),
    );
    renderCell({ descriptionEn: null });

    fireEvent.click(screen.getByRole('button', { name: 'Add English for 连体马桶' }));
    const input = screen.getByRole('textbox', { name: 'English for 连体马桶' });
    fireEvent.change(input, { target: { value: 'One-piece toilet' } });
    fireEvent.blur(input);

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
  });

  it('sends no request on blur when the value is unchanged', () => {
    renderCell({ descriptionEn: 'One-piece toilet' });

    fireEvent.click(screen.getByRole('button', { name: 'One-piece toilet' }));
    const input = screen.getByRole('textbox', { name: 'English for 连体马桶' });
    fireEvent.blur(input);

    expect(apiFetch).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'One-piece toilet' })).toBeInTheDocument();
  });
});

describe('DescriptionEnCell - a failed save toasts extractApiError\'s message', () => {
  it('shows the message the response body names, and stays editable', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse(
        { detail: { message: 'Enter the English wording before saving.', detail: 'target_text', code: null } },
        false,
        422,
      ),
    );
    renderCell({ descriptionEn: null });

    fireEvent.click(screen.getByRole('button', { name: 'Add English for 连体马桶' }));
    const input = screen.getByRole('textbox', { name: 'English for 连体马桶' });
    fireEvent.change(input, { target: { value: 'One-piece toilet' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Enter the English wording before saving.'),
    );
  });

  it('does not leave the cell dead: Enter again after a failure sends a second request (BLOCKER, review round)', async () => {
    apiFetch.mockResolvedValueOnce(
      jsonResponse({ detail: { message: 'Server error. Try again.', detail: null, code: null } }, false, 500),
    );
    renderCell({ descriptionEn: null });

    fireEvent.click(screen.getByRole('button', { name: 'Add English for 连体马桶' }));
    const input = screen.getByRole('textbox', { name: 'English for 连体马桶' });
    fireEvent.change(input, { target: { value: 'One-piece toilet' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Server error. Try again.'));
    // The cell must still be editable - a failed save leaves `editing` true - and focus
    // stays on the input rather than wherever the blur that preceded onError sent it.
    expect(input).toHaveFocus();

    apiFetch.mockResolvedValue(
      jsonResponse({
        source_text: '连体马桶',
        target_text: 'One-piece toilet',
        source: 'manual',
        rebound: { lines: 1, packing_rows: 0 },
      }),
    );
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
  });
});

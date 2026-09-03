/**
 * Contact Details -> Media Access (UAC S1-01, S1-02, S1-03).
 *
 * Mocks `apiFetch` (the api-client boundary), the same pattern
 * `ContactAttachmentTypesSection.test.tsx` uses, so the hook -> service -> fetch
 * chain is exercised for real and only the network is stubbed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactMediaAccessSection from './ContactMediaAccessSection';
import type { ContactMediaAccessItem } from '../services/contactMediaAccessService';

const apiFetch = vi.fn();

vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function ok(body: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function item(overrides: Partial<ContactMediaAccessItem> = {}): ContactMediaAccessItem {
  return {
    modality: 'image',
    is_allowed: false,
    has_row: false,
    monthly_limit: null,
    effective_monthly_limit: 50,
    max_clip_seconds: null,
    effective_max_clip_seconds: null,
    used: 0,
    remaining: 50,
    updated_at: null,
    updated_by_name: null,
    ...overrides,
  };
}

function accessResponse(items: ContactMediaAccessItem[]) {
  return { period_key: '2026-08', resets_on: '1 September', items };
}

/** GET vs PUT is dispatched on the request options `apiFetch` was actually called with. */
function mockApi(
  getBody: unknown,
  putResponder?: (body: Record<string, unknown>, url: string) => unknown,
) {
  apiFetch.mockImplementation((url: string, options?: { method?: string; body?: string }) => {
    if (options?.method === 'PUT') {
      const body = JSON.parse(options.body ?? '{}');
      return ok(putResponder ? putResponder(body, url) : { ...item(), ...body });
    }
    return ok(getBody);
  });
}

function renderWithClient(contactId = 'c1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactMediaAccessSection contactId={contactId} />
    </QueryClientProvider>,
  );
}

function putCalls() {
  return apiFetch.mock.calls.filter(
    (c) => (c[1] as { method?: string } | undefined)?.method === 'PUT',
  );
}

beforeEach(() => {
  apiFetch.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());

describe('ContactMediaAccessSection - S1-01/S1-02 always-present sections', () => {
  it('renders both modalities even with no rows and no usage, with an explicit empty state', async () => {
    mockApi(
      accessResponse([
        item({ modality: 'image' }),
        item({ modality: 'voice', effective_monthly_limit: 100, effective_max_clip_seconds: 120 }),
      ]),
    );
    renderWithClient();

    expect(await screen.findByText('Photos')).toBeInTheDocument();
    expect(screen.getByText('Voice notes')).toBeInTheDocument();
    expect(screen.getAllByText('Not enabled')).toHaveLength(2);
    expect(screen.getAllByText(/never configured/i)).toHaveLength(2);
  });

  it('turns access on in place, with no confirmation dialog', async () => {
    mockApi(
      accessResponse([
        item({ modality: 'image' }),
        item({ modality: 'voice', effective_monthly_limit: 100, effective_max_clip_seconds: 120 }),
      ]),
    );
    renderWithClient();
    await screen.findByText('Photos');

    fireEvent.click(screen.getByLabelText(/enable photos/i));

    await waitFor(() => {
      expect(putCalls()).toHaveLength(1);
    });
    expect(JSON.parse(putCalls()[0][1].body)).toEqual({
      is_allowed: true,
      monthly_limit: null,
      max_clip_seconds: null,
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });
});

describe('ContactMediaAccessSection - S1-03 turning access off', () => {
  it('confirms via AlertDialog before turning access off, and never calls window.confirm', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => {
      throw new Error('window.confirm must not be used - see AlertDialog / ADR CRUD standard');
    });
    mockApi(
      accessResponse([
        item({
          modality: 'image',
          is_allowed: true,
          has_row: true,
          monthly_limit: 250,
          effective_monthly_limit: 250,
        }),
        item({ modality: 'voice', effective_monthly_limit: 100, effective_max_clip_seconds: 120 }),
      ]),
    );
    renderWithClient();
    await screen.findByText('Photos');

    fireEvent.click(screen.getByLabelText(/enable photos/i));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toBeInTheDocument();
    expect(await screen.findByText('Turn off photos?')).toBeInTheDocument();
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(putCalls()).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: /^turn off$/i }));

    await waitFor(() => {
      expect(putCalls()).toHaveLength(1);
    });
    expect(JSON.parse(putCalls()[0][1].body)).toEqual({
      is_allowed: false,
      monthly_limit: 250,
      max_clip_seconds: null,
    });

    confirmSpy.mockRestore();
  });

  it('cancelling the confirmation makes no request', async () => {
    mockApi(
      accessResponse([
        item({ modality: 'image', is_allowed: true, has_row: true, effective_monthly_limit: 50 }),
        item({ modality: 'voice', effective_monthly_limit: 100, effective_max_clip_seconds: 120 }),
      ]),
    );
    renderWithClient();
    await screen.findByText('Photos');

    fireEvent.click(screen.getByLabelText(/enable photos/i));
    await screen.findByText('Turn off photos?');
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    expect(putCalls()).toHaveLength(0);
  });
});

describe('ContactMediaAccessSection - default hint and placeholder', () => {
  it('names the system default in the hint and placeholder when no override is set', async () => {
    mockApi(
      accessResponse([
        item({ modality: 'image', monthly_limit: null, effective_monthly_limit: 250 }),
        item({
          modality: 'voice',
          monthly_limit: null,
          effective_monthly_limit: 100,
          max_clip_seconds: null,
          effective_max_clip_seconds: 120,
        }),
      ]),
    );
    renderWithClient();
    await screen.findByText('Photos');

    fireEvent.click(screen.getByLabelText(/edit photos limits/i));
    const limitInput = await screen.findByLabelText('Monthly limit');
    expect(limitInput).toHaveAttribute('placeholder', '250');
    expect(screen.getByText('Blank uses the system default (250).')).toBeInTheDocument();
  });

  it('carries no default number in the hint once a monthly_limit override exists (no separate default was sent)', async () => {
    mockApi(
      accessResponse([
        item({
          modality: 'image',
          is_allowed: true,
          has_row: true,
          monthly_limit: 200,
          effective_monthly_limit: 200,
        }),
        item({ modality: 'voice', effective_monthly_limit: 100, effective_max_clip_seconds: 120 }),
      ]),
    );
    renderWithClient();
    await screen.findByText('Photos');

    fireEvent.click(screen.getByLabelText(/edit photos limits/i));
    const limitInput = await screen.findByLabelText('Monthly limit');
    expect(limitInput).toHaveAttribute('placeholder', '');
    expect(screen.getByText('Blank uses the system default.')).toBeInTheDocument();
  });

  it('names the system default clip seconds in the hint and placeholder when no override is set', async () => {
    mockApi(
      accessResponse([
        item({ modality: 'image' }),
        item({
          modality: 'voice',
          effective_monthly_limit: 100,
          max_clip_seconds: null,
          effective_max_clip_seconds: 120,
        }),
      ]),
    );
    renderWithClient();
    await screen.findByText('Voice notes');

    fireEvent.click(screen.getByLabelText(/edit voice notes limits/i));
    const clipInput = await screen.findByLabelText('Maximum clip seconds');
    expect(clipInput).toHaveAttribute('placeholder', '120');
    expect(
      screen.getByText(
        'Blank uses the system default (120s). A longer clip is refused before anything is spent.',
      ),
    ).toBeInTheDocument();
  });

  it('carries no default number in the clip-seconds hint once a max_clip_seconds override exists', async () => {
    mockApi(
      accessResponse([
        item({ modality: 'image' }),
        item({
          modality: 'voice',
          is_allowed: true,
          has_row: true,
          effective_monthly_limit: 100,
          max_clip_seconds: 45,
          effective_max_clip_seconds: 45,
        }),
      ]),
    );
    renderWithClient();
    await screen.findByText('Voice notes');

    fireEvent.click(screen.getByLabelText(/edit voice notes limits/i));
    const clipInput = await screen.findByLabelText('Maximum clip seconds');
    expect(clipInput).toHaveAttribute('placeholder', '');
    expect(
      screen.getByText(
        'Blank uses the system default. A longer clip is refused before anything is spent.',
      ),
    ).toBeInTheDocument();
  });
});

describe('ContactMediaAccessSection - limits dialog accessible description', () => {
  it.each([
    ['photos', /edit photos limits/i],
    ['voice notes', /edit voice notes limits/i],
  ])('gives the %s limits dialog an accessible description', async (_label, editLabel) => {
    mockApi(
      accessResponse([
        item({ modality: 'image', effective_monthly_limit: 250 }),
        item({ modality: 'voice', effective_monthly_limit: 100, effective_max_clip_seconds: 120 }),
      ]),
    );
    renderWithClient();
    await screen.findByText('Photos');

    fireEvent.click(screen.getByLabelText(editLabel));

    expect(
      await screen.findByText('Overrides the system default for this contact.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toHaveAccessibleDescription(
      'Overrides the system default for this contact.',
    );
  });
});

describe('ContactMediaAccessSection - bounds', () => {
  it('bounds the monthly limit override, disables Save on invalid input, and a blank value submits null', async () => {
    mockApi(
      accessResponse([
        item({
          modality: 'image',
          is_allowed: true,
          has_row: true,
          monthly_limit: 200,
          effective_monthly_limit: 200,
        }),
        item({ modality: 'voice', effective_monthly_limit: 100, effective_max_clip_seconds: 120 }),
      ]),
    );
    renderWithClient();
    await screen.findByText('Photos');
    fireEvent.click(screen.getByLabelText(/edit photos limits/i));

    const limitInput = await screen.findByLabelText('Monthly limit');
    const dialogSave = () => screen.getByRole('button', { name: /^Save media access$/i });

    fireEvent.change(limitInput, { target: { value: '100001' } });
    expect(
      screen.getByText('Enter a whole number between 0 and 100000, or leave it blank.'),
    ).toBeInTheDocument();
    expect(dialogSave()).toBeDisabled();

    fireEvent.change(limitInput, { target: { value: 'abc' } });
    expect(
      screen.getByText('Enter a whole number between 0 and 100000, or leave it blank.'),
    ).toBeInTheDocument();
    expect(dialogSave()).toBeDisabled();

    fireEvent.change(limitInput, { target: { value: '' } });
    expect(
      screen.queryByText('Enter a whole number between 0 and 100000, or leave it blank.'),
    ).not.toBeInTheDocument();
    expect(dialogSave()).toBeEnabled();

    fireEvent.click(dialogSave());

    await waitFor(() => {
      expect(putCalls()).toHaveLength(1);
    });
    expect(JSON.parse(putCalls()[0][1].body).monthly_limit).toBeNull();
  });
});

describe('ContactMediaAccessSection - a failed limits save', () => {
  it('keeps the dialog open, toasts, and never surfaces an unhandled rejection', async () => {
    const { toast } = await import('@/lib/toast');
    const unhandled: unknown[] = [];
    const onUnhandled = (event: PromiseRejectionEvent) => {
      unhandled.push(event.reason);
      event.preventDefault();
    };
    window.addEventListener('unhandledrejection', onUnhandled);
    process.on('unhandledRejection', onUnhandled as unknown as (reason: unknown) => void);

    apiFetch.mockImplementation((_url: string, options?: { method?: string }) => {
      if (options?.method === 'PUT') {
        return Promise.resolve({
          ok: false,
          status: 422,
          json: () => Promise.resolve({ detail: 'monthly_limit out of range' }),
        });
      }
      return ok(
        accessResponse([
          item({ modality: 'image', is_allowed: true, has_row: true }),
          item({ modality: 'voice' }),
        ]),
      );
    });
    renderWithClient();
    await screen.findByText('Photos');
    fireEvent.click(screen.getByLabelText(/edit photos limits/i));

    const limitInput = await screen.findByLabelText('Monthly limit');
    fireEvent.change(limitInput, { target: { value: '25' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save media access$/i }));

    await waitFor(() => expect(putCalls()).toHaveLength(1));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    // Let any rejection that was going to escape do so before asserting.
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(screen.getByLabelText('Monthly limit')).toBeInTheDocument();
    expect(unhandled).toEqual([]);

    window.removeEventListener('unhandledrejection', onUnhandled);
    process.off('unhandledRejection', onUnhandled as unknown as (reason: unknown) => void);
  });
});

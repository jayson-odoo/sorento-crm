/**
 * SPARE-PART-OR-B C, red-first (Phase 2). C5.1 / C5.4: each OR line has a Delivery date (the
 * shared date picker, dd/mm/yyyy) defaulting to the header date; the header field reads
 * "Delivery date" (no "Needed by" on OR screens).
 * Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md.
 * Mount and mocks copied from `SparePartRequestForm.sparePart.test.tsx`.
 *
 * NAMED CONTRACT CHOICES (the UAC leaves them open):
 * 1. The header picker's accessible name is "Delivery date"; each line's picker is the shared
 *    `DatePickerField` with ariaLabel "Delivery date for line <n>" (placeholder DD/MM/YYYY).
 * 2. The Products table carries a "Delivery date" column header.
 * 3. A new line ("Add product") starts on the header date; a header change fills only the
 *    lines still on the previous header date (C5.4).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/spare-part-requests/new',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  useHasAnyPermission: () => true,
  usePermissions: () => ({
    permissionSet: new Set(['procurement.spare_part_requests.create']),
    permissions: ['procurement.spare_part_requests.create'],
    isLoading: false,
    isError: false,
  }),
}));

const apiFetch = vi.fn(async (url: string) => {
  const payload = /lookup|select|options/.test(url) ? [] : { data: [], total: 0, pagination: { total: 0 } };
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import { SparePartRequestForm } from './SparePartRequestForm';

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestForm />
    </QueryClientProvider>,
  );
}

function typeDate(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } });
  fireEvent.blur(input);
}

function headerDate(): HTMLInputElement {
  return screen.getByLabelText(/^Delivery date$/) as HTMLInputElement;
}

function lineDate(n: number): HTMLInputElement {
  return screen.getByLabelText(`Delivery date for line ${n}`) as HTMLInputElement;
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('C5.1: the header field is "Delivery date"', () => {
  it('labels the header date "Delivery date" and never "Needed by"', async () => {
    mount();
    await screen.findByRole('button', { name: 'Submit' });
    expect(headerDate()).toBeInTheDocument();
    expect(screen.queryByText(/Needed by/i)).toBeNull();
  });
});

describe('C5.1: each line has a Delivery date', () => {
  it('the Products table has a Delivery date column', async () => {
    mount();
    expect(await screen.findByRole('columnheader', { name: /^Delivery date$/ })).toBeInTheDocument();
  });

  it('each line has the shared date picker, typed as dd/mm/yyyy', async () => {
    mount();
    await screen.findByRole('button', { name: 'Submit' });
    const input = lineDate(1);
    expect(input.getAttribute('type')).not.toBe('date');
    expect(input.getAttribute('placeholder')).toBe('DD/MM/YYYY');
    typeDate(input, '05/12/2026');
    expect(lineDate(1).value).toBe('05/12/2026');
  });

  it('a line starts on the header date', async () => {
    mount();
    await screen.findByRole('button', { name: 'Submit' });
    typeDate(headerDate(), '05/12/2026');
    expect(lineDate(1).value).toBe('05/12/2026');
    fireEvent.click(screen.getByRole('button', { name: /Add product/ }));
    expect(lineDate(2).value).toBe('05/12/2026');
  });
});

describe('C5.4: a header change fills only the lines still on the old header date', () => {
  it('keeps a line the requester moved and moves the others', async () => {
    mount();
    await screen.findByRole('button', { name: 'Submit' });
    typeDate(headerDate(), '05/12/2026');
    fireEvent.click(screen.getByRole('button', { name: /Add product/ }));
    typeDate(lineDate(1), '10/12/2026');
    typeDate(headerDate(), '20/12/2026');
    expect(lineDate(1).value).toBe('10/12/2026');
    expect(lineDate(2).value).toBe('20/12/2026');
  });
});

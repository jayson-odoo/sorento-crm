/**
 * LOOKUP-EMBED-CENTRAL review fix round 1 (F-13): the option dialog trusts the lookup set API's `alias_set` flag
 * (prop `aliasSet`) instead of a key list duplicated in the front end. Red before the dialog takes the prop.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

Element.prototype.scrollIntoView = vi.fn();
(Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import OptionFormDialog from '../components/OptionFormDialog';

const SET_ID = '8e3d5f4b-4444-4555-8666-c77788889999';
const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) });
const wrap = (ui: React.ReactElement) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation(async (url: string) =>
    String(url).includes('/alias-targets') ? json([{ value: 'ZZ Photo', label: 'ZZ Photo' }]) : json({}),
  );
});
afterEach(() => cleanup());

describe('alias_set flag', () => {
  it('a set the API says is an alias set gets the targets select, whatever its key', async () => {
    wrap(<OptionFormDialog open onOpenChange={() => {}} setId={SET_ID} setKey="some_future_alias" aliasSet editing={null} />);
    expect(await screen.findByRole('combobox')).toBeInTheDocument();
    expect(apiFetch.mock.calls.some(([url]) => String(url).includes('/alias-targets'))).toBe(true);
  });

  it('a set the API says is not an alias set stays a plain box even under a known alias key', async () => {
    wrap(<OptionFormDialog open onOpenChange={() => {}} setId={SET_ID} setKey="attachment_type_alias" aliasSet={false} editing={null} />);
    expect(await screen.findByText('Add option')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('combobox')).toBeNull());
    expect(apiFetch.mock.calls.some(([url]) => String(url).includes('/alias-targets'))).toBe(false);
  });
});

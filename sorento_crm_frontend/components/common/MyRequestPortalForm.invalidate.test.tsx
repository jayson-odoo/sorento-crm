/**
 * PORTAL-P4-REQUESTS: a write through the provider's client refetches the kind's CRM list
 * (those lists are staleTime: Infinity) and the my-requests key. One mechanism for every kind.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: (...a: unknown[]) => apiFetch(...a) };
});
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

import { MyRequestClientProvider } from '@/components/common/MyRequestPortalForm';
import { useSubmissionClient, type SubmissionClient } from '@/app/(auth)/portal/lib/submission-client';

let client: SubmissionClient;
function Grab() {
  client = useSubmissionClient();
  return null;
}
function res(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}
function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, 'invalidateQueries');
  render(
    <QueryClientProvider client={qc}>
      <MyRequestClientProvider>
        <Grab />
      </MyRequestClientProvider>
    </QueryClientProvider>,
  );
  return spy;
}
const keys = (spy: ReturnType<typeof setup>) =>
  spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey?: unknown })?.queryKey));

beforeEach(() => apiFetch.mockReset());

describe.each([
  ['complaint', 'complaints'],
  ['stock_inquiry', 'stock-inquiries'],
])('kind %s', (kind, listKey) => {
  it('saveDraft success invalidates the CRM list', async () => {
    apiFetch.mockResolvedValue(res(201, { id: 's1', status: 'draft', fields: {}, products: [] }));
    const spy = setup();
    await client.saveDraft(kind as never, {}, []);
    await waitFor(() => expect(keys(spy)).toContain(JSON.stringify([listKey])));
  });

  it('submitDraft success invalidates the CRM list', async () => {
    apiFetch.mockResolvedValue(res(200, { id: 's1', status: 'submitted', fields: {}, products: [] }));
    const spy = setup();
    await client.submitDraft(kind as never, 's1', {}, []);
    await waitFor(() => expect(keys(spy)).toContain(JSON.stringify([listKey])));
  });

  it('a failed save (422) does not invalidate', async () => {
    apiFetch.mockResolvedValue(res(422, { detail: 'bad' }));
    const spy = setup();
    await expect(client.saveDraft(kind as never, {}, [])).rejects.toBeTruthy();
    expect(keys(spy)).not.toContain(JSON.stringify([listKey]));
  });
});

describe('an R3 service write', () => {
  it('sampleRequest.createSampleRequest invalidates sample-requests', async () => {
    apiFetch.mockResolvedValue(res(201, { id: 'sr1' }));
    const spy = setup();
    await client.sampleRequest!.createSampleRequest({} as never);
    await waitFor(() => expect(keys(spy)).toContain(JSON.stringify(['sample-requests'])));
  });
});

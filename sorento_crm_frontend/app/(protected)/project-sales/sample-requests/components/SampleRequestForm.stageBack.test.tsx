/**
 * PROJECT-STAGE-ACTIONS: a new sample request opened from a project's Sample Submission stage
 * button goes back to that project's Samples Request tab on Cancel, not to the admin list.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const nav = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));

vi.mock('@/hooks/useRequestScope', () => ({
  useRequestScope: () => ({ limited: false, isLoading: false }),
}));

const mut = vi.hoisted(() => ({
  createAsync: vi.fn(),
  updateAsync: vi.fn(),
  submitAsync: vi.fn(),
  existing: { data: undefined as unknown, isLoading: false },
}));

vi.mock('../hooks/useSampleRequests', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useSampleRequests')>();
  return {
    ...actual,
    useSampleRequestMutations: () => ({
      create: { mutateAsync: mut.createAsync, isPending: false },
      update: { mutateAsync: mut.updateAsync, isPending: false },
      submit: { mutateAsync: mut.submitAsync, isPending: false },
    }),
    useSampleRequestQuery: () => mut.existing,
    useSampleRequestSwitches: () => ({ data: { requireProject: false } }),
  };
});

vi.mock('../services/sampleRequestService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/sampleRequestService')>();
  return {
    ...actual,
    searchSampleRequestProducts: vi.fn(async () => []),
    getSampleRequestQuotationPrefill: vi.fn(),
  };
});

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/projectService')>();
  return {
    ...actual,
    getProject: vi.fn(async () => ({ id: 'proj-1', project_code: 'PRJ-1', title: 'Tower' })),
    listProjects: vi.fn(async () => ({ data: [] })),
  };
});

vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService',
  () => ({ lookupCustomersForRequest: vi.fn(async () => []) }),
);

import { getSampleRequestQuotationPrefill } from '../services/sampleRequestService';
import SampleRequestForm from './SampleRequestForm';

function renderForm(props: { requestId?: string; projectId?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SampleRequestForm {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mut.existing = { data: undefined, isLoading: false };
  (getSampleRequestQuotationPrefill as ReturnType<typeof vi.fn>).mockResolvedValue({
    documents: [],
    document_id: null,
    issue_id: null,
    lines: [],
    skipped: [],
  });
});

describe('Cancel on a new sample request', () => {
  it('from a project goes back to its Samples Request tab', async () => {
    renderForm({ projectId: 'proj-1' });
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    expect(nav.push).toHaveBeenCalledWith('/project-sales/proj-1?tab=sample-requests');
  });

  it('without a project goes back to the list', async () => {
    renderForm();
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    expect(nav.push).toHaveBeenCalledWith('/project-sales/sample-requests');
  });
});

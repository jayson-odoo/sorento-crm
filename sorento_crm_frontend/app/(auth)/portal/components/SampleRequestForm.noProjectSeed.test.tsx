/**
 * PORTAL-P4-REQUESTS R3a (PAR-2): the portal's own SampleRequestForm is unchanged. With no provider and no
 * initial values it never seeds a project (the stage-action seed lives on the CRM side only), and every call
 * still goes to `/api/v1/public/portal` through portalFetch.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn() }),
  useSearchParams: () => new URLSearchParams('project_id=5b0c1d2e-aaaa-4bbb-8ccc-0123456789ab'),
}));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/project-sales/_shared/services/projectService', () => ({ getProject: vi.fn() }));

import { getProject } from '@/app/(protected)/project-sales/_shared/services/projectService';
import SampleRequestForm from './SampleRequestForm';

const fetched: Array<{ url: string; method: string; body: unknown }> = [];

beforeEach(() => {
  fetched.length = 0;
  vi.clearAllMocks();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      let body: unknown = init?.body;
      if (typeof body === 'string') {
        try { body = JSON.parse(body); } catch { /* keep */ }
      }
      fetched.push({ url: String(input), method: (init?.method ?? 'GET').toUpperCase(), body });
      return new Response(JSON.stringify({ id: 'new-1', status: 'draft', lines: [] }), { status: 200, headers: { 'content-type': 'application/json' } });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe('portal SampleRequestForm with no provider', () => {
  it('Save as draft POSTs /api/v1/public/portal/submissions/sample_request with no project_id and never reads a project', async () => {
    render(<SampleRequestForm />);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(fetched.some((c) => c.method === 'POST')).toBe(true));
    const post = fetched.find((c) => c.method === 'POST')!;
    expect(post.url).toContain('/api/v1/public/portal/submissions/sample_request');
    expect(post.url).not.toContain('/my-requests');
    expect((post.body as { project_id?: string | null }).project_id ?? null).toBeNull();
    expect(getProject).not.toHaveBeenCalled();
    await waitFor(() => expect(nav.replace).toHaveBeenCalled());
    expect(String(nav.replace.mock.calls[0][0])).toContain('/sample_request/new-1');
    expect(String(nav.replace.mock.calls[0][0])).not.toContain('/project-sales');
  });
});

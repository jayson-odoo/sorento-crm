/**
 * PORTAL-P4-REQUESTS R1 guard (green today, must stay green): a SubmissionForm with NO SubmissionClientProvider
 * still talks to the PORTAL API with the portal token. The CRM injection must not change the portal.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));

import { SubmissionForm } from './SubmissionForm';
import { json, ME, SI_DETAIL } from './__fixtures__/crmSubmissionApi';

type Call = { url: string; method: string; token: string | null };
const calls: Call[] = [];

beforeEach(() => {
  calls.length = 0;
  window.localStorage.setItem('sorento.portalToken', 'tok-portal');
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase();
      const h = new Headers(init?.headers || {});
      calls.push({ url: String(url), method, token: h.get('X-Portal-Token') });
      const path = String(url).split('?')[0];
      if (path.endsWith('/portal/me')) return json({ ...ME });
      if (path.endsWith('/lookups/products')) return json([{ product_code: 'PRD-1', product_name: 'P', category_id: null }]);
      if (path.includes('/lookups/sets/')) return json({ options: [], default_value: null });
      if (path.endsWith('/neighbours')) return json({ prev_id: null, next_id: null, position: 1, total: 1 });
      if (path.endsWith('/revisions') || path.endsWith('/comments')) return json({ items: [] });
      if (path.endsWith('/portal/attachments')) return json({ link_id: 'l1', attachment_id: 'a1', filename: 'f.pdf', size: 3, url: 'u', uploader_kind: 'contact', can_unlink: true });
      if (path.endsWith('/submit')) return json(SI_DETAIL({ status: 'pending_purchasing', is_draft: false }));
      if (path.includes('/portal/submissions/stock_inquiry')) return json(SI_DETAIL());
      return json({});
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

const portalCalls = () => calls.filter((c) => c.url.startsWith('/api/v1/public/portal/'));

describe('SubmissionForm without a provider talks to the portal API', () => {
  it('a product lookup goes to /api/v1/public/portal/lookups/products with the portal token', async () => {
    render(<SubmissionForm kind="stock_inquiry" />);
    const code = await screen.findByPlaceholderText('Search products...');
    fireEvent.change(code, { target: { value: 'PR' } });
    await waitFor(() => expect(calls.some((c) => c.url.includes('/api/v1/public/portal/lookups/products'))).toBe(true), { timeout: 3000 });
    const hit = calls.find((c) => c.url.includes('/lookups/products'))!;
    expect(hit.token).toBe('tok-portal');
    expect(calls.filter((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });

  it('an upload on a draft goes to /api/v1/public/portal/attachments', async () => {
    const { container } = render(<SubmissionForm kind="stock_inquiry" submissionId="si-5" />);
    await waitFor(() => expect(document.getElementById('product_code')).not.toBeNull());
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).not.toBeNull();
    const file = new File(['abc'], 'f.pdf', { type: 'application/pdf' });
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/api/v1/public/portal/attachments') && c.method === 'POST')).toBe(true));
    expect(calls.filter((c) => c.url.startsWith('/api/v1/my-requests'))).toHaveLength(0);
  });

  it('Save as draft and Submit go to /api/v1/public/portal/submissions/stock_inquiry', async () => {
    render(<SubmissionForm kind="stock_inquiry" submissionId="si-5" />);
    await waitFor(() => expect(document.getElementById('product_code')).not.toBeNull());
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(portalCalls().some((c) => c.method === 'PUT' && c.url.endsWith('/submissions/stock_inquiry/si-5'))).toBe(true));
    fireEvent.click(await screen.findByRole('button', { name: /^Submit/ }));
    await act(async () => { await new Promise((r) => setTimeout(r, 150)); });
    const dialog = screen.queryByRole('dialog') ?? screen.queryByRole('alertdialog');
    const confirm = dialog && Array.from(dialog.querySelectorAll('button')).find((b) => /submit|confirm|yes|send/i.test(b.textContent ?? ''));
    if (confirm) fireEvent.click(confirm);
    await waitFor(() => expect(portalCalls().some((c) => c.method === 'POST' && c.url.endsWith('/stock_inquiry/si-5/submit'))).toBe(true));
  });
});

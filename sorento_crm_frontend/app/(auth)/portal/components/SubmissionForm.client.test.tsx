/**
 * PORTAL-P4-REQUESTS R1: SubmissionForm and its children read every API call through the injected
 * SubmissionClient (`../lib/submission-client`: `SubmissionClientProvider` with a `client` prop and
 * `useSubmissionClient()`; the client mirrors portal-client function for function). Default = portal-client.
 * Red today: the module does not exist, SF imports portal-client directly.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));

import * as portalClient from '../lib/portal-client';
import { SubmissionClientProvider, useSubmissionClient } from '../lib/submission-client';
import { SubmissionForm } from './SubmissionForm';
import { ME, SI_DETAIL } from './__fixtures__/crmSubmissionApi';

function stubClient() {
  return {
    ...portalClient,
    fetchMe: vi.fn(async () => ({ ...ME })),
    fetchSubmission: vi.fn(async () => SI_DETAIL() as never),
    fetchSubmissionNeighbours: vi.fn(async () => ({ prev_id: null, next_id: null, position: 1, total: 1 })),
    fetchRevisions: vi.fn(async () => []),
    fetchSubmissionComments: vi.fn(async () => []),
    lookupProducts: vi.fn(async () => [{ product_code: 'PRD-1', product_name: 'P', category_id: null }]),
    lookupDebtors: vi.fn(async () => []),
    lookupSet: vi.fn(async () => ({ options: [], defaultValue: null })),
    saveDraft: vi.fn(async () => SI_DETAIL() as never),
    submitDraft: vi.fn(async () => SI_DETAIL() as never),
    uploadAttachment: vi.fn(async () => ({ link_id: 'l', attachment_id: 'a', filename: 'f.pdf', size: 1, uploader_kind: 'contact', can_unlink: true })),
  };
}

let fetchSpy: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchSpy = vi.fn(async () => new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }));
  vi.stubGlobal('fetch', fetchSpy);
});
afterEach(() => vi.unstubAllGlobals());

describe('SubmissionClient context', () => {
  it('the default client is portal-client', () => {
    let got: unknown;
    function Probe() {
      got = useSubmissionClient();
      return null;
    }
    render(<Probe />);
    expect((got as typeof portalClient).lookupProducts).toBe(portalClient.lookupProducts);
    expect((got as typeof portalClient).saveDraft).toBe(portalClient.saveDraft);
  });

  it('a provided client serves the profile, the product lookup and the draft save; the portal API is never hit', async () => {
    const client = stubClient();
    render(
      <SubmissionClientProvider client={client as never}>
        <SubmissionForm kind="stock_inquiry" />
      </SubmissionClientProvider>,
    );
    await waitFor(() => expect(client.fetchMe).toHaveBeenCalled());
    fireEvent.change(await screen.findByPlaceholderText('Search products...'), { target: { value: 'PR' } });
    await waitFor(() => expect(client.lookupProducts).toHaveBeenCalled(), { timeout: 3000 });
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(client.saveDraft).toHaveBeenCalled());
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    expect(fetchSpy.mock.calls.filter((c) => String(c[0]).includes('/api/v1/public/portal'))).toHaveLength(0);
  });

  it('children use the provided client too: a saved draft loads revisions and comments through it, and uploads through it', async () => {
    const client = stubClient();
    const { container } = render(
      <SubmissionClientProvider client={client as never}>
        <SubmissionForm kind="stock_inquiry" submissionId="si-5" />
      </SubmissionClientProvider>,
    );
    await waitFor(() => expect(client.fetchSubmission).toHaveBeenCalled());
    await waitFor(() => expect(client.fetchRevisions).toHaveBeenCalled());
    await waitFor(() => expect(document.getElementById('product_code')).not.toBeNull());
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [new File(['abc'], 'f.pdf', { type: 'application/pdf' })] } });
    });
    await waitFor(() => expect(client.uploadAttachment).toHaveBeenCalled());
    expect(fetchSpy.mock.calls.filter((c) => String(c[0]).includes('/api/v1/public/portal'))).toHaveLength(0);
  });
});

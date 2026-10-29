/**
 * PS-REGISTER-CHECK-FIRST AC-G8: the Documents tab upload dialog has a Kind select, Project Document
 * (default) and Requirements. The kind is looked up by code (legacy types have a null code), the
 * attachments POST carries that type's id, and the list shows each file's kind.
 * Drives the real service through apiFetch so the test pins the wire, not a function name.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/hooks/usePermissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/usePermissions')>()),
  useHasPermission: () => true,
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

type Call = { url: string; method: string; body: unknown };
const calls: Call[] = [];
const TYPES = [
  { id: 'ty-legacy', type_name: 'Old Thing', code: null },
  { id: 'ty-doc', type_name: 'Project Document', code: 'project_document' },
  { id: 'ty-req', type_name: 'Requirements', code: 'project_requirements' },
];
const DOCS = [
  {
    id: 'd1',
    original_filename: 'brief.pdf',
    stored_filename: 'brief.pdf',
    file_path: 'https://cdn.example/brief.pdf',
    file_size_bytes: 2048,
    mime_type: 'application/pdf',
    uploaded_at: '2026-10-20T01:00:00',
    attachment_type: { id: 'ty-req', type_name: 'Requirements' },
  },
  {
    id: 'd2',
    original_filename: 'drawing.pdf',
    stored_filename: 'drawing.pdf',
    file_path: 'https://cdn.example/drawing.pdf',
    file_size_bytes: 4096,
    mime_type: 'application/pdf',
    uploaded_at: '2026-10-21T01:00:00',
    attachment_type: { id: 'ty-doc', type_name: 'Project Document' },
  },
];

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiFetch: async (input: string, init: RequestInit = {}) => {
      const method = (init.method ?? 'GET').toUpperCase();
      calls.push({ url: String(input), method, body: init.body ?? null });
      const ok = (b: unknown) =>
        new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
      if (method === 'GET' && String(input).includes('attachment-types')) return ok({ data: TYPES });
      if (method === 'GET') return ok({ data: DOCS });
      if (method === 'POST') return ok({ id: 'new' });
      return ok({});
    },
  };
});

import { ProjectDocumentsPanel } from './ProjectDocumentsPanel';
import type { Project } from '../../_shared/types/project.types';

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const project = { id: 'proj-1', can_edit: true } as unknown as Project;
  return render(
    <QueryClientProvider client={client}>
      <ProjectDocumentsPanel project={project} />
    </QueryClientProvider>,
  );
}
const uploadPosts = () => calls.filter((c) => c.method === 'POST' && c.url.includes('/attachments'));
const sentTypeId = (c: Call) => (c.body as FormData).get('attachment_type_id');

async function openDialog() {
  renderPanel();
  fireEvent.click(await screen.findByRole('button', { name: /Upload documents/ }));
  const dialog = await screen.findByRole('dialog');
  const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, {
    target: { files: [new File(['x'], 'reqs.pdf', { type: 'application/pdf' })] },
  });
  return dialog;
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
});

describe('AC-G8 Documents tab kind', () => {
  it('AC-G8 the list shows each file kind (Requirements / Project Document)', async () => {
    renderPanel();
    await screen.findByText('brief.pdf');
    expect(screen.getAllByText('Requirements').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Project Document').length).toBeGreaterThan(0);
  });

  it('AC-G8 the upload dialog has a Kind select defaulting to Project Document', async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: /Upload documents/ }));
    const dialog = await screen.findByRole('dialog');
    const kind = within(dialog).getByRole('combobox', { name: /Kind/ });
    expect(kind).toHaveTextContent('Project Document');
  });

  it('AC-G8 with the default kind the POST carries the Project Document type id', async () => {
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole('button', { name: /^Upload/ }));
    await waitFor(() => expect(uploadPosts()).toHaveLength(1));
    expect(sentTypeId(uploadPosts()[0])).toBe('ty-doc');
  });

  it('AC-G8 picking Requirements sends the type whose code is project_requirements', async () => {
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole('combobox', { name: /Kind/ }));
    fireEvent.click(await screen.findByRole('option', { name: 'Requirements' }));
    fireEvent.click(within(dialog).getByRole('button', { name: /^Upload/ }));
    await waitFor(() => expect(uploadPosts()).toHaveLength(1));
    expect(sentTypeId(uploadPosts()[0])).toBe('ty-req');
  });
});

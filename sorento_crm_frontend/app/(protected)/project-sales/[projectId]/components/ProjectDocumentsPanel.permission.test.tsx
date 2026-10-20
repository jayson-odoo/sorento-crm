/**
 * ATTACH-DELETE-PERM: the Project Documents trash icon calls the library's single delete,
 * which the server gates on `resource.attachments.delete`. The icon shows only to a project
 * editor holding that slug, so nobody else is offered a delete that would answer 403.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const perm = vi.hoisted(() => ({ canDelete: true }));
vi.mock('@/hooks/usePermissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/usePermissions')>()),
  useHasPermission: (slug: string) => slug !== 'resource.attachments.delete' || perm.canDelete,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('../../_shared/services/projectDocumentService', () => ({
  listProjectDocuments: vi.fn().mockResolvedValue([
    {
      id: 'doc-1',
      original_filename: 'zzt-drawing.pdf',
      stored_filename: 'zzt-drawing.pdf',
      file_path: 'https://cdn.example/zzt-drawing.pdf',
      file_size_bytes: 2048,
      mime_type: 'application/pdf',
      uploaded_at: '2026-10-20T01:00:00',
    },
  ]),
  deleteProjectDocument: vi.fn(),
  resolveProjectDocumentTypeId: vi.fn(),
  uploadProjectDocument: vi.fn(),
}));

import { ProjectDocumentsPanel } from './ProjectDocumentsPanel';
import type { Project } from '../../_shared/types/project.types';

function renderPanel(canEdit: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const project = { id: 'proj-1', can_edit: canEdit } as unknown as Project;
  return render(
    <QueryClientProvider client={client}>
      <ProjectDocumentsPanel project={project} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  perm.canDelete = true;
});

describe('ProjectDocumentsPanel delete follows resource.attachments.delete', () => {
  it('an editor holding the slug sees the delete icon', async () => {
    renderPanel(true);
    expect(await screen.findByRole('button', { name: 'Delete zzt-drawing.pdf' })).toBeInTheDocument();
  });

  it('an editor without the slug sees no delete icon', async () => {
    perm.canDelete = false;
    renderPanel(true);
    expect(await screen.findByText('zzt-drawing.pdf')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete zzt-drawing.pdf' })).not.toBeInTheDocument();
  });

  it('a non-editor sees no delete icon even with the slug', async () => {
    renderPanel(false);
    expect(await screen.findByText('zzt-drawing.pdf')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete zzt-drawing.pdf' })).not.toBeInTheDocument();
  });
});

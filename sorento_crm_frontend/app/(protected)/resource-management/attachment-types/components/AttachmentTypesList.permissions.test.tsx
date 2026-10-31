/**
 * AttachmentTypesList - the Add, Edit and Delete controls follow the slugs the server checks
 * (AGENTIC-KNOWLEDGE fix round 2, S-d). The type routes are permission gated now, so a viewer
 * must not be offered buttons that can only answer 403.
 *
 * Slugs: `resource.attachment_types.add` / `.edit` / `.delete` (the registry's CRUD names).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

const held = vi.hoisted(() => ({ slugs: new Set<string>() }));

vi.mock('@/hooks/usePermissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/usePermissions')>()),
  useHasPermission: (slug: string) => held.slugs.has(slug),
}));

vi.mock('../hooks/useAttachmentTypes', () => ({
  useAttachmentTypes: () => ({
    data: {
      data: [
        {
          id: 'type-1',
          type_name: 'Employee Handbook',
          description: null,
          allowed_extensions: 'pdf,docx',
          max_file_size_mb: 10,
          max_count_per_entity: null,
          created_at: '2026-01-01T00:00:00',
        },
      ],
      pagination: { total: 1, page: 1, limit: 50 },
    },
    isLoading: false,
    isFetching: false,
    isPlaceholderData: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock('./AttachmentTypeFormDialog', () => ({ default: () => null }));
vi.mock('./AttachmentTypeDeleteDialog', () => ({ default: () => null }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/resource-management/attachment-types',
}));

import AttachmentTypesList from './AttachmentTypesList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AttachmentTypesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  held.slugs = new Set();
});

describe('AttachmentTypesList - permissions', () => {
  it('a viewer sees the rows but no Add, Edit or Delete', async () => {
    renderList();

    expect(await screen.findByText('Employee Handbook')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Create Attachment Type|Add/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Delete attachment type/i })).not.toBeInTheDocument();
  });

  it('the add slug shows Add only', async () => {
    held.slugs = new Set(['resource.attachment_types.add']);
    renderList();

    await screen.findByText('Employee Handbook');
    expect(screen.getByRole('button', { name: /Create Attachment Type|Add/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Delete attachment type/i })).not.toBeInTheDocument();
  });

  it('the edit slug shows Edit only', async () => {
    held.slugs = new Set(['resource.attachment_types.edit']);
    renderList();

    await screen.findByText('Employee Handbook');
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Create Attachment Type|Add/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Delete attachment type/i })).not.toBeInTheDocument();
  });

  it('the delete slug shows Delete only', async () => {
    held.slugs = new Set(['resource.attachment_types.delete']);
    renderList();

    await screen.findByText('Employee Handbook');
    expect(screen.getByRole('button', { name: /Delete attachment type/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Create Attachment Type|Add/i })).not.toBeInTheDocument();
  });

  it('all three slugs show all three controls', async () => {
    held.slugs = new Set([
      'resource.attachment_types.add',
      'resource.attachment_types.edit',
      'resource.attachment_types.delete',
    ]);
    renderList();

    await screen.findByText('Employee Handbook');
    expect(screen.getByRole('button', { name: /Create Attachment Type|Add/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Delete attachment type/i })).toBeInTheDocument();
  });
});

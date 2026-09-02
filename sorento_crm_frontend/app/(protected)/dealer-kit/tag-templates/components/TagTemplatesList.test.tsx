/**
 * TagTemplatesList - checkbox selection + bulk Delete as a deferred action
 * (PLAN-price-tag-feedback-r2.md D26, S11; UAC AC-S11-1).
 *
 * The engine (park/countdown/commit/cancel) is `hooks/useDeferredAction.test.tsx`'s
 * job - this only pins that the list:
 *   - shows the bulk Delete action once rows are selected, not before;
 *   - wires the right action key/entity type and the selected ids into it;
 *   - clears the selection once the batch is parked;
 *   - refetches the list once the batch commits (`onCommitted`).
 *
 * `DataGrid` fetches column preferences via `useListingColumnPreferences` - real
 * network under jsdom would hang the row body forever, so it is mocked exactly
 * as `SPOAllocationsList.test.tsx` mocks it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
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
  usePathname: () => '/dealer-kit/tag-templates',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const listTemplates = vi.fn();
const deleteTemplate = vi.fn();
const createTemplate = vi.fn();
vi.mock('../../services/tagTemplateService', () => ({
  listTemplates: (...a: unknown[]) => listTemplates(...a),
  deleteTemplate: (...a: unknown[]) => deleteTemplate(...a),
  createTemplate: (...a: unknown[]) => createTemplate(...a),
}));

// The engine itself is `hooks/useDeferredAction.test.tsx`'s job - this only pins
// that the LIST wires the right action key, entity type and ids into it (AC-S11-1).
const deletionStart = vi.fn();
const useDeferredActionInput = vi.fn();
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (input: unknown) => {
    useDeferredActionInput(input);
    return {
      pending: null,
      isPending: false,
      isBlocked: false,
      start: deletionStart,
      cancel: vi.fn(),
      countdown: null,
    };
  },
}));

import { TagTemplatesList } from './TagTemplatesList';
import type { TagTemplate } from '@/lib/dealer-kit/tag-template-types';

function template(over: Partial<TagTemplate> = {}): TagTemplate {
  return {
    id: 'tmpl-1',
    name: 'Toilet tag',
    family: 'toilet',
    doc: { layers: [], width_mm: 85, height_mm: 58 },
    print_size: { width_mm: 85, height_mm: 58 },
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    published_version_id: null,
    published_version_no: null,
    ...over,
  };
}

async function renderList() {
  // `ConfirmDeleteDialog` (the per-row delete, unchanged by this slice) calls
  // `useQueryClient()` even while closed, so a real provider is required.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={client}>
      <TagTemplatesList />
    </QueryClientProvider>,
  );
  // Let the initial `listTemplates()` fetch resolve and the grid re-render.
  await screen.findByText(/New Template/i);
  return utils;
}

const rows = () => within(document.querySelector('tbody') as HTMLElement);

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  listTemplates.mockResolvedValue([
    template({ id: 'tmpl-1', name: 'Toilet tag' }),
    template({ id: 'tmpl-2', name: 'Basin tag' }),
  ]);
});

describe('TagTemplatesList - bulk delete toolbar (AC-S11-1)', () => {
  it('does not show a Delete action with nothing selected', async () => {
    await renderList();

    expect(screen.queryByRole('button', { name: /^Delete$/i })).toBeNull();
  });

  it('shows Delete once a row is selected', async () => {
    await renderList();

    fireEvent.click(rows().getAllByRole('checkbox')[0]);

    expect(await screen.findByRole('button', { name: /^Delete$/i })).toBeInTheDocument();
  });

  it('configures the deferred action with the bulk_delete action key and entity type', async () => {
    await renderList();

    fireEvent.click(rows().getAllByRole('checkbox')[0]);
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/i }));

    const lastInput = useDeferredActionInput.mock.calls[
      useDeferredActionInput.mock.calls.length - 1
    ][0] as { actionKey: string; entityType: string };
    expect(lastInput.actionKey).toBe('tag_template.bulk_delete');
    expect(lastInput.entityType).toBe('tag_template');
  });

  it('Delete queues the deferred action with every selected id, and clears the selection', async () => {
    await renderList();

    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/i }));

    expect(deletionStart).toHaveBeenCalledTimes(1);
    const lastInput = useDeferredActionInput.mock.calls[
      useDeferredActionInput.mock.calls.length - 1
    ][0] as { payload: { template_ids: string[] }; entityId: string | null };
    expect(lastInput.payload.template_ids.sort()).toEqual(['tmpl-1', 'tmpl-2']);
    expect(lastInput.entityId).toBeTruthy();

    // The selection is cleared right after parking - the bulk strip goes with it.
    expect(screen.queryByRole('button', { name: /^Delete$/i })).toBeNull();
  });

  it('completion refetches the list', async () => {
    await renderList();
    expect(listTemplates).toHaveBeenCalledTimes(1);

    fireEvent.click(rows().getAllByRole('checkbox')[0]);
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/i }));

    const lastInput = useDeferredActionInput.mock.calls[
      useDeferredActionInput.mock.calls.length - 1
    ][0] as { onCommitted?: () => void };
    lastInput.onCommitted?.();

    expect(listTemplates).toHaveBeenCalledTimes(2);
  });
});

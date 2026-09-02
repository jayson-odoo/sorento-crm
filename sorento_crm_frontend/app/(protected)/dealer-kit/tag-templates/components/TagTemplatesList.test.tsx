/**
 * TagTemplatesList - delete, one row or a selection, as a deferred action
 * (PLAN-price-tag-feedback-r2.md D26, S11; UAC AC-S11-1).
 *
 * Mocked at the SERVICE boundary (`pendingActionService`) rather than at the hook,
 * so the thing under test is what the list actually does with the grace window:
 * which action key it parks, which ids travel with it, what the countdown is asked
 * to say, and which rows dim while it runs. A hook-level mock could not answer the
 * last two, and they are the half of D26 that was missing.
 *
 * The engine itself (park / countdown / commit / cancel) is
 * `hooks/useDeferredAction.test.tsx`'s job and is not re-tested here.
 *
 * `DataGrid` fetches column preferences via `useListingColumnPreferences` - real
 * network under jsdom would hang the row body forever, so it is mocked exactly
 * as `SPOAllocationsList.test.tsx` mocks it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
  within,
} from '@testing-library/react';
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

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    dismiss: vi.fn(),
  },
}));

const listTemplates = vi.fn();
const createTemplate = vi.fn();
vi.mock('../../services/tagTemplateService', () => ({
  listTemplates: (...a: unknown[]) => listTemplates(...a),
  createTemplate: (...a: unknown[]) => createTemplate(...a),
}));

/** Every countdown toast raised, with the copy it was given. */
const raisedToasts: { verb: string; subject: string }[] = [];
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: (input: { pending: { id: string }; verb: string; subject: string }) => {
    raisedToasts.push({ verb: input.verb, subject: input.subject });
    return `pending-action-${input.pending.id}`;
  },
  dismissDeferredToast: vi.fn(),
}));

const createPendingAction = vi.fn();
const cancelPendingAction = vi.fn();
const getCurrentPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: (...args: unknown[]) => cancelPendingAction(...args),
  getCurrentPendingAction: (...args: unknown[]) => getCurrentPendingAction(...args),
}));

import { TagTemplatesList } from './TagTemplatesList';
import { pendingEntityStore, pendingEntityKey } from '@/lib/pending-entity-store';
import type { TagTemplate } from '@/lib/dealer-kit/tag-template-types';

function template(over: Partial<TagTemplate> = {}): TagTemplate {
  return {
    id: 'tmpl-1',
    name: 'Toilet tag',
    family: 'wc',
    doc: { layers: [], width_mm: 85, height_mm: 58 },
    print_size: { width_mm: 85, height_mm: 58 },
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    published_version_id: null,
    published_version_no: null,
    ...over,
  };
}

/** A naive-UTC timestamp `offsetMs` from now, the way the backend writes them. */
function serverTime(offsetMs: number): string {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d+Z$/, '');
}

async function renderList() {
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

/** The action the server is currently holding, as `current` would answer it. */
let parked: {
  id: string;
  action_key: string;
  entity_type: string;
  entity_id: string;
  commit_at: string;
  window_seconds: number;
} | null = null;
const parkedBody = () => createPendingAction.mock.calls[0][0];

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  raisedToasts.length = 0;
  pendingEntityStore.reset();
  listTemplates.mockResolvedValue([
    template({ id: 'tmpl-1', name: 'Toilet tag' }),
    template({ id: 'tmpl-2', name: 'Basin tag' }),
  ]);
  parked = null;
  createPendingAction.mockImplementation(async (input) => {
    parked = {
      id: 'action-1',
      action_key: input.actionKey,
      entity_type: input.entityType,
      entity_id: input.entityId,
      commit_at: serverTime(10_000),
      window_seconds: 10,
    };
    return parked;
  });
  // The countdown is the SERVER's: the hook believes `current`, not its own click,
  // so a poll answering "nothing is parked" would end the action mid-test.
  getCurrentPendingAction.mockImplementation(async (_type: string, entityId: string) => ({
    pending: parked && parked.entity_id === entityId ? parked : null,
    last_outcome: null,
  }));
});

afterEach(() => {
  pendingEntityStore.reset();
});

describe('TagTemplatesList - bulk delete (AC-S11-1, D26)', () => {
  it('does not show a Delete action with nothing selected', async () => {
    await renderList();

    expect(screen.queryByRole('button', { name: /^Delete$/i })).toBeNull();
  });

  it('shows Delete once a row is selected', async () => {
    await renderList();

    fireEvent.click(rows().getAllByRole('checkbox')[0]);

    expect(await screen.findByRole('button', { name: /^Delete$/i })).toBeInTheDocument();
  });

  it('parks ONE bulk action carrying every selected id, and clears the selection', async () => {
    await renderList();

    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/i }));

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(1));
    const body = parkedBody();
    expect(body.actionKey).toBe('tag_template.bulk_delete');
    expect(body.entityType).toBe('tag_template');
    expect([...body.payload.template_ids].sort()).toEqual(['tmpl-1', 'tmpl-2']);
    // The batch is keyed on a token naming the CLICK, never on one of the rows.
    expect(body.entityId).toBeTruthy();
    expect(['tmpl-1', 'tmpl-2']).not.toContain(body.entityId);

    // The selection is cleared right after parking - the bulk strip goes with it.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /^Delete$/i })).toBeNull(),
    );
  });

  it('asks NOTHING: no dialog is opened by Delete, only a countdown (D26)', async () => {
    await renderList();

    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/i }));

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it("the countdown names the COUNT, because a selection has no single record's name", async () => {
    await renderList();

    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/i }));

    await waitFor(() => expect(raisedToasts).toHaveLength(1));
    expect(raisedToasts[0]).toEqual({ verb: 'Deleting', subject: '2 templates' });
  });

  it('dims EVERY selected row for the length of the window (D26)', async () => {
    await renderList();

    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/i }));

    await waitFor(() =>
      expect(pendingEntityStore.getKeys().has(pendingEntityKey('tag_template', 'tmpl-1'))).toBe(
        true,
      ),
    );
    expect(
      pendingEntityStore.getKeys().has(pendingEntityKey('tag_template', 'tmpl-2')),
    ).toBe(true);
    // And the grid says so on the rows themselves, not only in the store.
    await waitFor(() =>
      expect(document.querySelectorAll('tbody tr[data-pending="true"]')).toHaveLength(2),
    );
  });

  it('Cancel takes the dimming off every row it put it on', async () => {
    await renderList();

    fireEvent.click(screen.getByLabelText('Select all rows on this page'));
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/i }));
    await waitFor(() =>
      expect(pendingEntityStore.getKeys().has(pendingEntityKey('tag_template', 'tmpl-1'))).toBe(
        true,
      ),
    );

    // What the toast's Cancel does once the server has withdrawn the action.
    pendingEntityStore.releaseById('action-1');

    expect(pendingEntityStore.getKeys().size).toBe(0);
    await waitFor(() =>
      expect(document.querySelectorAll('tbody tr[data-pending="true"]')).toHaveLength(0),
    );
  });

  it('a one-row selection says "1 template", not "1 templates"', async () => {
    await renderList();

    fireEvent.click(rows().getAllByRole('checkbox')[0]);
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/i }));

    await waitFor(() => expect(raisedToasts).toHaveLength(1));
    expect(raisedToasts[0].subject).toBe('1 template');
  });
});

describe('TagTemplatesList - the per-row Delete (D7)', () => {
  it('parks the single-record action for that row, with no dialog', async () => {
    await renderList();

    fireEvent.click(rows().getAllByLabelText('Delete template')[0]);

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(1));
    const body = parkedBody();
    expect(body.actionKey).toBe('tag_template.delete');
    expect(body.entityType).toBe('tag_template');
    expect(body.entityId).toBe('tmpl-1');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('names the template in its countdown, and dims only that row', async () => {
    await renderList();

    fireEvent.click(rows().getAllByLabelText('Delete template')[0]);

    await waitFor(() => expect(raisedToasts).toHaveLength(1));
    expect(raisedToasts[0]).toEqual({ verb: 'Deleting', subject: 'Toilet tag' });
    await waitFor(() =>
      expect(document.querySelectorAll('tbody tr[data-pending="true"]')).toHaveLength(1),
    );
  });
});

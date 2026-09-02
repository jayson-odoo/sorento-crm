/**
 * SavedViewsMenu - the generic segments dropdown (S4, PLAN-scm-reorder-oi-feedback-1sep.md).
 *
 * Generalised from `components/reports/ReportViewsMenu.test.tsx`'s shape (Mine/Shared,
 * publish permission absent-not-disabled), plus two things S4 adds that `ReportViewsMenu`
 * does not have:
 *
 * - AC-4.2: a segment stores the FULL view (filters + sort + visible columns + column
 *   order); applying it hands the caller that config back UNCHANGED. Restoring the screen
 *   from it is the caller's own job (`PlanLinesGrid.tsx`'s `applySegment`) - this
 *   component's whole contract to that caller is passing the four-part config through
 *   intact, which is what is asserted here.
 * - AC-4.4: a personal default auto-applies on open when the reader set one; a published
 *   default applies for a reader with none; a view already applied (e.g. restored from
 *   URL state) is never overridden.
 * - D7: delete runs through the deferred-action countdown (`useDeferredRowAction`,
 *   `saved_view.delete`), never a confirmation dialog - the one difference from
 *   `ReportViewsMenu`, which kept a `ConfirmDeleteDialog` (S6b explicitly did not migrate
 *   it, see that component's own comment).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuItem: ({
    children,
    onClick,
    disabled,
  }: React.PropsWithChildren<{ onClick?: () => void; disabled?: boolean }>) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
}));

const fetchSavedViews = vi.fn();
const createSavedView = vi.fn();
const publishSavedView = vi.fn();
const setDefaultSavedView = vi.fn();

vi.mock('@/services/savedViewsService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/savedViewsService')>();
  return {
    ...actual,
    fetchSavedViews: (...a: unknown[]) => fetchSavedViews(...a),
    createSavedView: (...a: unknown[]) => createSavedView(...a),
    publishSavedView: (...a: unknown[]) => publishSavedView(...a),
    setDefaultSavedView: (...a: unknown[]) => setDefaultSavedView(...a),
  };
});

const permission = vi.hoisted(() => ({ canPublish: true }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => permission.canPublish,
}));

const deferred = vi.hoisted(() => ({ run: vi.fn(), inputs: [] as Record<string, unknown>[] }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: Record<string, unknown>) => {
    deferred.inputs.push(input);
    return { run: deferred.run, targetId: null, isPending: false };
  },
}));

const getUserListColumnConfig = vi.fn();
const upsertUserListColumnConfig = vi.fn();
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (...a: unknown[]) => getUserListColumnConfig(...a),
  upsertUserListColumnConfig: (...a: unknown[]) => upsertUserListColumnConfig(...a),
}));

import { SavedViewsMenu } from './SavedViewsMenu';
import type { SavedView, SavedViewConfig } from '@/services/savedViewsService';

const LISTING_KEY = 'zzt.dashboard.view::second-listing';

// AC-4.2's whole point: a config with all four parts populated, carried through unchanged.
const CONFIG: SavedViewConfig = {
  filters: { op: 'and', children: [{ field_key: 'supplier', op: 'eq', value: 'Acme' }] },
  sort: [{ id: 'suggested_qty', desc: true }],
  columns: ['sku', 'supplier', 'suggested_qty'],
  column_order: ['sku', 'supplier', 'suggested_qty'],
};

const MINE_PRIVATE: SavedView = {
  id: 'v-private',
  name: 'My segment',
  is_shared: false,
  is_default: false,
  owner_name: 'You',
  view: CONFIG,
};

const MINE_PUBLISHED: SavedView = {
  id: 'v-published',
  name: 'Slow movers',
  is_shared: true,
  is_default: false,
  owner_name: 'You',
  view: CONFIG,
};

const THEIRS_DEFAULT: SavedView = {
  id: 'v-theirs',
  name: 'Management default',
  is_shared: true,
  is_default: true,
  owner_name: 'Chin Wei Loon',
  view: CONFIG,
};

const THEIRS_NOT_DEFAULT: SavedView = { ...THEIRS_DEFAULT, is_default: false };

function render(props: Partial<React.ComponentProps<typeof SavedViewsMenu>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onApply = vi.fn();
  const utils = rtlRender(
    <QueryClientProvider client={client}>
      <SavedViewsMenu
        listingKey={LISTING_KEY}
        currentViewId={null}
        currentConfig={CONFIG}
        onApply={onApply}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onApply };
}

beforeEach(() => {
  vi.clearAllMocks();
  deferred.inputs = [];
  permission.canPublish = true;
  fetchSavedViews.mockResolvedValue({ mine: [MINE_PRIVATE, MINE_PUBLISHED], shared: [THEIRS_DEFAULT] });
  getUserListColumnConfig.mockResolvedValue({ listing_key: LISTING_KEY, config: null });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('SavedViewsMenu - lists Mine and Shared', () => {
  it('keeps a published view of mine under Mine, badged rather than moved', async () => {
    render();

    expect(await screen.findByText('My segment')).toBeInTheDocument();
    expect(screen.getByText('Slow movers')).toBeInTheDocument();
    expect(screen.getByText('Management default')).toBeInTheDocument();
    expect(screen.getAllByText('Shared')).toHaveLength(2); // section heading + badge
    expect(screen.getByText('Default')).toBeInTheDocument();
  });

  it('reaches the SECOND listing key the caller supplied, not any reorder key', async () => {
    render();
    await waitFor(() => expect(fetchSavedViews).toHaveBeenCalledWith(LISTING_KEY));
    expect(fetchSavedViews).not.toHaveBeenCalledWith(
      expect.stringContaining('reorder-plan-lines'),
    );
  });

  it('says so when there is nothing saved yet', async () => {
    fetchSavedViews.mockResolvedValue({ mine: [], shared: [] });
    render();

    expect(await screen.findByText('No saved segments yet')).toBeInTheDocument();
    expect(screen.getByText('No shared segments yet')).toBeInTheDocument();
  });
});

describe('SavedViewsMenu - AC-4.2 applying restores the FULL view', () => {
  it('hands the caller filters, sort, columns and column order UNCHANGED', async () => {
    // No default candidate here, so the auto-apply effect (AC-4.4) does not fire and
    // steal the first onApply call before the click under test does.
    fetchSavedViews.mockResolvedValue({ mine: [MINE_PRIVATE, MINE_PUBLISHED], shared: [] });
    const { onApply } = render();
    await screen.findByText('My segment');

    fireEvent.click(screen.getByText('My segment'));

    expect(onApply).toHaveBeenCalledWith(MINE_PRIVATE);
    const passed = onApply.mock.calls[0][0] as SavedView;
    expect(passed.view.filters).toEqual(CONFIG.filters);
    expect(passed.view.sort).toEqual(CONFIG.sort);
    expect(passed.view.columns).toEqual(CONFIG.columns);
    expect(passed.view.column_order).toEqual(CONFIG.column_order);
  });

  it('"No segment" applies null, clearing whatever was applied', async () => {
    fetchSavedViews.mockResolvedValue({ mine: [MINE_PRIVATE], shared: [] });
    const { onApply } = render({ currentViewId: 'v-private' });
    // "My segment" is both the trigger label and the menu item once currentViewId is set.
    await waitFor(() => expect(screen.getAllByText('My segment').length).toBeGreaterThan(1));

    fireEvent.click(screen.getByText('No segment'));

    expect(onApply).toHaveBeenCalledWith(null);
  });
});

describe('SavedViewsMenu - AC-4.4 defaults on open', () => {
  it('auto-applies the reader personal default when one is set', async () => {
    getUserListColumnConfig.mockResolvedValue({
      listing_key: LISTING_KEY,
      config: { defaultSavedViewId: 'v-published' },
    });
    const { onApply } = render();
    await waitFor(() => expect(onApply).toHaveBeenCalledWith(MINE_PUBLISHED));
  });

  it('falls back to the published default when the reader has no personal default', async () => {
    const { onApply } = render();
    await waitFor(() => expect(onApply).toHaveBeenCalledWith(THEIRS_DEFAULT));
  });

  it('does nothing when neither a personal nor a published default exists', async () => {
    fetchSavedViews.mockResolvedValue({ mine: [MINE_PRIVATE], shared: [THEIRS_NOT_DEFAULT] });
    const { onApply } = render();
    await waitFor(() => expect(fetchSavedViews).toHaveBeenCalled());
    expect(onApply).not.toHaveBeenCalled();
  });

  it('never overrides a view already applied (e.g. restored from URL state)', async () => {
    const { onApply } = render({ currentViewId: 'v-private' });
    await waitFor(() => expect(fetchSavedViews).toHaveBeenCalled());
    expect(onApply).not.toHaveBeenCalled();
  });

  it('S3 (PR #489 review round): a FAILED personal-default fetch still lets the ' +
    'published default apply', async () => {
    // Gating on `personalConfig === undefined` left this stuck forever on a failed
    // fetch (undefined never became defined); gating on `isFetched` (settled either
    // way) is what makes the published default reach a reader whose own config GET
    // errored, rather than silently doing nothing for them alone.
    getUserListColumnConfig.mockRejectedValue(new Error('network error'));
    const { onApply } = render();
    await waitFor(() => expect(onApply).toHaveBeenCalledWith(THEIRS_DEFAULT));
  });
});

describe('SavedViewsMenu - saving the current shape', () => {
  it('saves under a name', async () => {
    createSavedView.mockResolvedValue({ ...MINE_PRIVATE, name: 'Q3 review' });
    fetchSavedViews.mockResolvedValue({ mine: [], shared: [] });
    render();

    fireEvent.click(screen.getByRole('button', { name: 'Save view' }));
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Q3 review' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(createSavedView).toHaveBeenCalledWith(LISTING_KEY, { name: 'Q3 review', view: CONFIG }),
    );
  });
});

describe('SavedViewsMenu - publish permission is ABSENT, never disabled', () => {
  it('offers Publish on an unshared view of mine when I may publish', async () => {
    publishSavedView.mockResolvedValue({ ...MINE_PRIVATE, is_shared: true });
    fetchSavedViews.mockResolvedValue({ mine: [MINE_PRIVATE], shared: [] });
    render({ currentViewId: 'v-private' });

    fireEvent.click(await screen.findByText('Publish as shared'));

    await waitFor(() => expect(publishSavedView).toHaveBeenCalledWith('v-private', true));
  });

  it('offers Set as default on an already-shared view', async () => {
    setDefaultSavedView.mockResolvedValue({ ...MINE_PUBLISHED, is_default: true });
    fetchSavedViews.mockResolvedValue({ mine: [MINE_PUBLISHED], shared: [] });
    render({ currentViewId: 'v-published' });

    fireEvent.click(await screen.findByText('Set as default for everyone'));

    await waitFor(() => expect(setDefaultSavedView).toHaveBeenCalledWith('v-published'));
  });

  it('hides both publishing actions entirely without the permission', async () => {
    permission.canPublish = false;
    fetchSavedViews.mockResolvedValue({ mine: [MINE_PRIVATE], shared: [] });
    render({ currentViewId: 'v-private' });

    await waitFor(() => expect(screen.getAllByText('My segment').length).toBeGreaterThan(1));
    expect(screen.queryByText('Publish as shared')).not.toBeInTheDocument();
    expect(screen.queryByText('Set as default for everyone')).not.toBeInTheDocument();
  });
});

describe('SavedViewsMenu - delete runs through the deferred-action countdown (D7)', () => {
  it('parks the delete with the record id and name, never a confirm dialog', async () => {
    fetchSavedViews.mockResolvedValue({ mine: [MINE_PRIVATE], shared: [] });
    render({ currentViewId: 'v-private' });

    fireEvent.click(await screen.findByText('Delete view'));

    expect(deferred.run).toHaveBeenCalledWith({ id: 'v-private', subject: 'My segment' });
    expect(screen.queryByText('Confirm delete')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: /delete/i })).not.toBeInTheDocument();
  });

  it('the hook is wired to the saved_view.delete record action', () => {
    render({ currentViewId: 'v-private' });
    expect(deferred.inputs[0]).toMatchObject({ actionKey: 'saved_view.delete', entityType: 'saved_view' });
  });

  it('does not offer to delete somebody else published view', async () => {
    fetchSavedViews.mockResolvedValue({ mine: [], shared: [THEIRS_DEFAULT] });
    render({ currentViewId: 'v-theirs' });

    await waitFor(() => expect(screen.getAllByText('Management default').length).toBeGreaterThan(1));
    expect(screen.queryByText('Delete view')).not.toBeInTheDocument();
  });
});

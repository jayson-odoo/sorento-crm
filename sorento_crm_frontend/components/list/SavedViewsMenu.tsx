'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Check, ChevronDown, Pin, Share2, Star, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { FormDialogScaffold } from '@/components/common/FormDialogScaffold';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { useHasPermission } from '@/hooks/usePermissions';
import { useSavedViewMutations, useSavedViews } from '@/hooks/useSavedViews';
import { upsertUserListColumnConfig } from '@/lib/listing-column-preferences/listColumnPreferencesService';
import {
  USER_LIST_COLUMN_CONFIG_QUERY_KEY_PREFIX,
  useUserListColumnConfigQuery,
} from '@/lib/listing-column-preferences/useUserListColumnConfigQuery';
import {
  SAVED_VIEWS_QUERY_KEY,
  type SavedView,
  type SavedViewConfig,
} from '@/services/savedViewsService';

/** Publish permission slug (`app/services/saved_views_service.py:PUBLISH_PERMISSION`). */
export const SAVED_VIEWS_PUBLISH_PERMISSION = 'list_query.saved_views.publish';

/** The SAME key `useListingColumnPreferences`/`useListingViewPreferences` use, so the
 *  personal-default read below shares their cache entry rather than a second GET. */
const CONFIG_QUERY_KEY_PREFIX = USER_LIST_COLUMN_CONFIG_QUERY_KEY_PREFIX;

/**
 * The saved-views (segments) dropdown, beside Filters (AC-4.4) - generalised from
 * `ReportViewsMenu` (S4, PLAN-scm-reorder-oi-feedback-1sep.md).
 *
 * Reusable by design: a caller supplies only `listingKey`, the config currently on
 * screen (to Save), and `onApply` - the SAME three inputs on any listing (AC-4.5).
 *
 * Two defaults, per G9:
 * - **Personal** - which of MY OWN views (mine or shared) I want on open. No permission
 *   needed; stored in the SAME per-user per-listing blob column preferences already use
 *   (`defaultSavedViewId`), never in `saved_views` itself.
 * - **Published** - the listing's default for everyone. Requires
 *   `list_query.saved_views.publish` and mirrors `report_views`' one-shared-default rule
 *   (`SavedViewsService.set_default`).
 *
 * On mount, a personal default wins if set; otherwise the published default applies for
 * a user with none (AC-4.4). Delete runs through the deferred-action countdown
 * (`saved_view.delete`), never a confirmation dialog.
 */
export function SavedViewsMenu({
  listingKey,
  currentViewId,
  currentConfig,
  onApply,
}: {
  listingKey: string;
  currentViewId: string | null;
  currentConfig: SavedViewConfig;
  onApply: (view: SavedView | null) => void;
}) {
  const queryClient = useQueryClient();
  const { data: views } = useSavedViews(listingKey);
  const { create, publish, setDefault } = useSavedViewMutations(listingKey);
  const canPublish = useHasPermission(SAVED_VIEWS_PUBLISH_PERMISSION);

  const { data: personalConfig, isFetched: personalConfigFetched } =
    useUserListColumnConfigQuery(listingKey);
  const myDefaultId = personalConfig?.config?.defaultSavedViewId ?? null;

  const [saveOpen, setSaveOpen] = useState(false);
  const [name, setName] = useState('');

  const mine = useMemo(() => views?.mine ?? [], [views]);
  const shared = useMemo(() => views?.shared ?? [], [views]);
  const all = useMemo(() => [...mine, ...shared], [mine, shared]);
  const current = useMemo(
    () => all.find((v) => v.id === currentViewId) ?? null,
    [all, currentViewId],
  );
  const currentIsMine = Boolean(current && mine.some((v) => v.id === current.id));

  // The current view is the only one this menu ever parks a delete on, so a commit here
  // always means it: clear the applied filter/sort/columns the deleted view had set.
  const deleteAction = useDeferredRowAction({
    actionKey: 'saved_view.delete',
    entityType: 'saved_view',
    verb: 'Deleting',
    successMessage: 'View deleted',
    invalidateKeys: [[SAVED_VIEWS_QUERY_KEY, listingKey]],
    onCommitted: () => onApply(null),
  });

  // Auto-apply on open (AC-4.4), once views + the personal-default blob have both
  // SETTLED (S3, PR #489 review round: `isFetched` - true whether the GET succeeded
  // or failed - rather than `personalConfig === undefined`, which stayed undefined
  // forever on a failed fetch and meant the published default never applied for
  // that reader), and only while nothing has been picked yet - a caller with a view
  // already applied (e.g. restored from URL state) must not be overridden.
  const appliedOnceRef = useRef(false);
  useEffect(() => {
    if (appliedOnceRef.current || !views || !personalConfigFetched) return;
    appliedOnceRef.current = true;
    if (currentViewId) return;
    const personal = myDefaultId ? all.find((v) => v.id === myDefaultId) : undefined;
    const published = all.find((v) => v.is_default);
    const resolved = personal ?? published;
    if (resolved) onApply(resolved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [views, personalConfigFetched]);

  const setMyDefault = (id: string | null) => {
    upsertUserListColumnConfig(listingKey, { defaultSavedViewId: id })
      .then(() => queryClient.invalidateQueries({ queryKey: [CONFIG_QUERY_KEY_PREFIX, listingKey] }))
      .catch(() => toast.error('Could not save your default view'));
  };

  const save = (event: React.FormEvent) => {
    event.preventDefault();
    create.mutate(
      { name, view: currentConfig },
      {
        onSuccess: (view) => {
          setSaveOpen(false);
          setName('');
          onApply(view);
        },
      },
    );
  };

  /** `showOwner` is set on the Shared list only: a column of bare names says nothing
   *  about whose view each one is, and on my own list the answer is always me. */
  const renderItem = (view: SavedView, showOwner = false) => (
    <DropdownMenuItem key={view.id} onClick={() => onApply(view)} className="gap-2">
      <Check className={view.id === currentViewId ? 'size-4 opacity-100' : 'size-4 opacity-0'} />
      <span className="min-w-0 flex-1">
        <span className="block truncate" title={view.name}>
          {view.name}
        </span>
        {showOwner && view.owner_name && (
          <span className="block truncate text-xs text-muted-foreground" title={view.owner_name}>
            {view.owner_name}
          </span>
        )}
      </span>
      <span className="ms-auto flex shrink-0 items-center gap-1">
        {view.id === myDefaultId && (
          <Badge variant="outline" size="sm" title="Your default on this list">
            Mine
          </Badge>
        )}
        {view.is_shared && mine.some((v) => v.id === view.id) && (
          <Badge variant="outline" size="sm">
            Shared
          </Badge>
        )}
        {view.is_default && (
          <Badge variant="secondary" size="sm">
            Default
          </Badge>
        )}
      </span>
    </DropdownMenuItem>
  );

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5">
            <span className="max-w-40 truncate" title={current?.name ?? 'No segment'}>
              {current?.name ?? 'No segment'}
            </span>
            <ChevronDown className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>Mine</DropdownMenuLabel>
          {mine.length > 0 ? (
            mine.map((view) => renderItem(view))
          ) : (
            <DropdownMenuItem disabled>No saved segments yet</DropdownMenuItem>
          )}

          <DropdownMenuSeparator />
          <DropdownMenuLabel>Shared</DropdownMenuLabel>
          {shared.length > 0 ? (
            shared.map((view) => renderItem(view, true))
          ) : (
            <DropdownMenuItem disabled>No shared segments yet</DropdownMenuItem>
          )}

          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => onApply(null)} className="gap-2">
            <Check className={currentViewId ? 'size-4 opacity-0' : 'size-4 opacity-100'} />
            No segment
          </DropdownMenuItem>

          {current && (
            <DropdownMenuItem
              onClick={() => setMyDefault(myDefaultId === current.id ? null : current.id)}
              className="gap-2"
            >
              <Pin className="size-4" />
              {myDefaultId === current.id ? 'Unset as my default' : 'Set as my default'}
            </DropdownMenuItem>
          )}
          {current && canPublish && !current.is_shared && (
            <DropdownMenuItem
              onClick={() => publish.mutate({ id: current.id, isShared: true })}
              className="gap-2"
            >
              <Share2 className="size-4" />
              Publish as shared
            </DropdownMenuItem>
          )}
          {current && canPublish && current.is_shared && !current.is_default && (
            <DropdownMenuItem onClick={() => setDefault.mutate(current.id)} className="gap-2">
              <Star className="size-4" />
              Set as default for everyone
            </DropdownMenuItem>
          )}
          {current && currentIsMine && (
            <DropdownMenuItem
              onClick={() => deleteAction.run({ id: current.id, subject: current.name })}
              className="gap-2 text-destructive"
            >
              <Trash2 className="size-4" />
              Delete view
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <Button variant="outline" size="sm" onClick={() => setSaveOpen(true)}>
        Save view
      </Button>

      <FormDialogScaffold
        open={saveOpen}
        onOpenChange={(open) => {
          setSaveOpen(open);
          if (!open) setName('');
        }}
        title="Save view"
        submitLabel="Save"
        onSubmit={save}
        isPending={create.isPending}
      >
        <div>
          <Label htmlFor="saved-view-name">Name</Label>
          <Input
            id="saved-view-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="My segment"
            className="mt-1"
            autoFocus
          />
        </div>
      </FormDialogScaffold>
    </>
  );
}

export default SavedViewsMenu;

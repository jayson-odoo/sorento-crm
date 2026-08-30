'use client';

import { useMemo, useState } from 'react';
import { Check, ChevronDown, Share2, Star, Trash2 } from 'lucide-react';
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
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { FormDialogScaffold } from '@/components/common/FormDialogScaffold';
import { useReportViewMutations, useReportViews } from '@/hooks/useReports';
import { REPORT_VIEWS_KEY, type ReportView, type ReportViewConfig } from '@/services/reportService';

/**
 * Saved views: personal by default, shared when published, one shared view the default
 * for everyone.
 *
 * Mine is what the caller OWNS, published ones included (badged Shared); Shared is OTHER
 * people's published views. A view leaving its author's own list the moment they share it
 * is how somebody loses the view they just made.
 *
 * Publish and Set as default are ABSENT without `reports.views.publish`, not disabled
 * (AC-C4): a greyed-out control the user can never earn is only an invitation to ask
 * why it is greyed out.
 */
export function ReportViewsMenu({
  reportKey,
  canPublish,
  currentViewId,
  currentConfig,
  onApply,
}: {
  reportKey: string;
  canPublish: boolean;
  currentViewId: string | null;
  currentConfig: ReportViewConfig;
  onApply: (view: ReportView | null) => void;
}) {
  const { data: views } = useReportViews(reportKey);
  const { create, remove, publish, setDefault } = useReportViewMutations(reportKey);

  const [saveOpen, setSaveOpen] = useState(false);
  const [name, setName] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);

  const mine = useMemo(() => views?.mine ?? [], [views]);
  const shared = useMemo(() => views?.shared ?? [], [views]);
  const current = useMemo(
    () => [...mine, ...shared].find((v) => v.id === currentViewId) ?? null,
    [mine, shared, currentViewId],
  );
  const currentIsMine = Boolean(current && mine.some((v) => v.id === current.id));

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

  /**
   * `showOwner` is set on the Shared list only: a column of bare names says nothing about
   * whose view each one is, and on my own list the answer is always me.
   */
  const renderItem = (view: ReportView, showOwner = false) => (
    <DropdownMenuItem key={view.id} onClick={() => onApply(view)} className="gap-2">
      <Check className={view.id === currentViewId ? 'size-4 opacity-100' : 'size-4 opacity-0'} />
      <span className="min-w-0 flex-1">
        <span className="block truncate" title={view.name}>
          {view.name}
        </span>
        {showOwner && view.owner_name && (
          <span
            className="block truncate text-xs text-muted-foreground"
            title={view.owner_name}
          >
            {view.owner_name}
          </span>
        )}
      </span>
      <span className="ms-auto flex shrink-0 items-center gap-1">
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
          <Button variant="outline" className="gap-1.5">
            <span className="max-w-40 truncate" title={current?.name ?? 'Report default'}>
              {current?.name ?? 'Report default'}
            </span>
            <ChevronDown className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>Mine</DropdownMenuLabel>
          {mine.length > 0 ? (
            // Wrapped rather than passed to map directly: map hands its callback the INDEX
            // as a second argument, which would land in `showOwner`.
            mine.map((view) => renderItem(view))
          ) : (
            <DropdownMenuItem disabled>No saved views yet</DropdownMenuItem>
          )}

          <DropdownMenuSeparator />
          <DropdownMenuLabel>Shared</DropdownMenuLabel>
          {shared.length > 0 ? (
            shared.map((view) => renderItem(view, true))
          ) : (
            <DropdownMenuItem disabled>No shared views yet</DropdownMenuItem>
          )}

          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => onApply(null)} className="gap-2">
            <Check className={currentViewId ? 'size-4 opacity-0' : 'size-4 opacity-100'} />
            Report default
          </DropdownMenuItem>

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
              onClick={() => setDeleteOpen(true)}
              className="gap-2 text-destructive"
            >
              <Trash2 className="size-4" />
              Delete view
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <Button variant="outline" onClick={() => setSaveOpen(true)}>
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
          <Label htmlFor="report-view-name">Name</Label>
          <Input
            id="report-view-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Management default"
            className="mt-1"
            autoFocus
          />
        </div>
      </FormDialogScaffold>

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete view"
        description={`Delete "${current?.name ?? ''}"? This cannot be undone.`}
        successMessage="View deleted"
        queryKeysToInvalidate={[[REPORT_VIEWS_KEY, reportKey]]}
        onDelete={async () => {
          if (current) await remove.mutateAsync(current.id);
        }}
        onSuccess={() => onApply(null)}
      />
    </>
  );
}

'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import {
  useProject,
  useQuotationMutations,
  useQuotations,
} from '../../../../_shared/hooks/useProjects';
import { OutcomePill } from '../../../../_shared/components/OutcomePill';
import { QuotationDialog } from '../../../components/QuotationDialog';
import { QuotationOutcomeDialog } from '../../../components/QuotationOutcomeDialog';
import { QuotationVersionEditor } from '../../../components/QuotationVersionEditor';

/**
 * One priced scope: its revisions, and the lines on whichever revision is open.
 *
 * Reads the scope out of the project's quotation LIST rather than fetching it by id, because
 * no by-id endpoint exists and the list is already cached by the tab the user clicked from.
 * A direct hit on this URL simply fetches that list once.
 */
export function QuotationDetailClient({
  projectId,
  quotationId,
}: {
  projectId: string;
  quotationId: string;
}) {
  const router = useRouter();
  const project = useProject(projectId);
  const quotations = useQuotations(projectId);
  const { remove } = useQuotationMutations(projectId);

  const [editing, setEditing] = React.useState(false);
  const [deciding, setDeciding] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);

  const quotation = (quotations.data ?? []).find((row) => row.id === quotationId) ?? null;

  if (quotations.isLoading || project.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!quotation || !project.data) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This quotation could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          It may have been deleted.
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href={`/project-sales/${projectId}?tab=quotations`}>Back to quotations</Link>
        </Button>
      </div>
    );
  }

  const canEdit = project.data.can_edit;

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">{project.data.project_code}</span>
            <OutcomePill outcome={quotation.outcome} />
          </div>
          <h1 className="mt-1 text-xl font-semibold break-words">{quotation.scope_label}</h1>
          <p className="text-sm text-muted-foreground break-words">
            {[
              `${quotation.version_count} revision${quotation.version_count === 1 ? '' : 's'}`,
              quotation.series_name,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>

        {canEdit && (
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" onClick={() => setDeciding(true)}>
              {quotation.outcome === 'open' ? 'Record outcome' : 'Change outcome'}
            </Button>
            <DetailActionsMenu ariaLabel="Quotation actions">
              <DropdownMenuItem onSelect={() => setEditing(true)}>Edit scope</DropdownMenuItem>
              <DropdownMenuItem
                variant="destructive"
                onSelect={() => setConfirmDelete(true)}
              >
                <Trash2 className="size-4" aria-hidden />
                Delete scope
              </DropdownMenuItem>
            </DetailActionsMenu>
          </div>
        )}
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Revisions</CardTitle>
        </CardHeader>
        <CardContent>
          <QuotationVersionEditor project={project.data} quotation={quotation} />
        </CardContent>
      </Card>

      {editing && (
        <QuotationDialog
          project={project.data}
          quotation={quotation}
          onDone={() => setEditing(false)}
        />
      )}

      {deciding && (
        <QuotationOutcomeDialog
          project={project.data}
          quotation={quotation}
          onDone={() => setDeciding(false)}
        />
      )}

      <ConfirmDeleteDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Confirm delete"
        description={`Delete the "${quotation.scope_label}" quotation and all ${quotation.version_count} of its versions? This action cannot be undone, and the project's outcome will be recalculated without it.`}
        onDelete={async () => {
          await remove.mutateAsync(quotation.id);
        }}
        onSuccess={() => router.push(`/project-sales/${projectId}?tab=quotations`)}
        successMessage="Quotation deleted"
      />
    </div>
  );
}

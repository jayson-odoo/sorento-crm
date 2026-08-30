'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Pencil, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { usePartyMutations, useProjectParties } from '../../../_shared/hooks/useProjects';
import type { ProjectParty } from '../../../_shared/types/project.types';
import { PartyFormDialog } from '../../components/PartyFormDialog';
import { TYPE_HINT, TYPE_LABEL } from '../../components/partyTypes';

/**
 * One organisation, read in full.
 *
 * Every section is rendered whether or not it holds anything, with an explicit empty
 * state saying what is missing and why it matters. A section that disappears on missing
 * data teaches people that the field does not exist.
 *
 * The record is read out of the parties LIST rather than a per-record endpoint: the
 * master is small, the list is already cached by the screen the user arrived from, and
 * there is no single-party route to call. Same query, same cache key, no extra request.
 */
export function PartyDetailClient({ partyId }: { partyId: string }) {
  const router = useRouter();
  const [editing, setEditing] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);

  const parties = useProjectParties({ include_inactive: true, limit: 200 });
  const { remove } = usePartyMutations();

  const party: ProjectParty | null = React.useMemo(
    () => (parties.data?.data ?? []).find((row) => row.id === partyId) ?? null,
    [parties.data, partyId],
  );

  if (parties.isLoading) {
    return (
      <div className="space-y-5" data-testid="party-detail-loading">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (parties.isError) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This party could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {parties.error instanceof Error ? parties.error.message : 'Try again shortly.'}
        </p>
        <Button
          type="button"
          variant="outline"
          className="mt-4"
          onClick={() => void parties.refetch()}
        >
          Try again
        </Button>
      </div>
    );
  }

  if (!party) {
    return (
      <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
        <h2 className="text-sm font-semibold">This party no longer exists</h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          It was deleted, or the link is out of date. The projects it appeared on keep
          the name they were registered with.
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href="/project-sales/parties">Back to parties</Link>
        </Button>
      </div>
    );
  }

  const typeLabel = TYPE_LABEL[party.party_type] ?? party.party_type;
  const typeHint = TYPE_HINT[party.party_type];
  const projectCount = party.project_count ?? 0;

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <Button asChild variant="ghost" size="sm" className="-ms-2 mb-1 gap-1.5">
            <Link href="/project-sales/parties">
              <ArrowLeft className="size-4" aria-hidden />
              Parties
            </Link>
          </Button>
          <h2 className="text-xl font-semibold">{party.name}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <Badge variant="secondary">{typeLabel}</Badge>
            {party.is_active ? (
              <Badge variant="outline">Active</Badge>
            ) : (
              <Badge variant="secondary">Inactive</Badge>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" onClick={() => setEditing(true)}>
            <Pencil className="size-4" aria-hidden />
            Edit
          </Button>
          <Button type="button" variant="outline" onClick={() => setDeleting(true)}>
            <Trash2 className="size-4 text-destructive" aria-hidden />
            Delete
          </Button>
        </div>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Identity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label="Type" value={typeLabel} hint={typeHint} />
            <Field
              label="Registration no."
              value={party.registration_no}
            />
            <Field
              label="Status"
              value={party.is_active ? 'Active' : 'Inactive'}
              hint={
                party.is_active
                  ? 'Offered in every project picker.'
                  : 'Stays on its projects, but no longer offered in pickers.'
              }
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Contact</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field
              label="Phone"
              value={party.phone}
            />
            <Field label="Email" value={party.email} />
            <Field label="Address" value={party.address} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Commercial</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field
              label="Buys as"
              value={party.customer_name}
              empty="Not a buyer. This firm influences the specification but never places the order."
            />
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground">Projects</p>
              {projectCount > 0 ? (
                <p className="text-sm font-medium tabular-nums">
                  {projectCount} project{projectCount === 1 ? '' : 's'}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  None yet. Register a project against this firm and the count follows.
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Notes</CardTitle>
          </CardHeader>
          <CardContent>
            {party.notes ? (
              <p className="whitespace-pre-wrap break-words text-sm">{party.notes}</p>
            ) : (
              <p className="text-sm text-muted-foreground">
                Nothing written down. Who to speak to, what they specify and past history
                belong here, so the next person does not start cold.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {editing && <PartyFormDialog party={party} onDone={() => setEditing(false)} />}

      <ConfirmDeleteDialog
        open={deleting}
        onOpenChange={setDeleting}
        title="Confirm delete"
        description={`Delete "${party.name}"? This action cannot be undone. A party used as a developer on any project cannot be deleted, so deactivate it instead.`}
        onDelete={async () => {
          await remove.mutateAsync(party.id);
        }}
        onSuccess={() => router.push('/project-sales/parties')}
        successMessage="Party deleted"
      />
    </div>
  );
}

function Field({
  label,
  value,
  hint,
  empty,
}: {
  label: string;
  value?: string | null;
  hint?: string;
  empty?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      {value ? (
        <p className="break-words text-sm font-medium">{value}</p>
      ) : (
        <p className="text-sm text-muted-foreground">{empty ?? '-'}</p>
      )}
      {value && hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

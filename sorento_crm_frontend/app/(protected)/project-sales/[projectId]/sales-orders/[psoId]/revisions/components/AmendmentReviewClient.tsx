'use client';

import * as React from 'react';
import Link from 'next/link';
import { GitCompareArrows } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useAmendment,
  useAmendmentAutocountChangeList,
  useAmendmentAutocountChangeListExport,
  useAmendmentMutations,
  usePoVersions,
  useProjectSalesOrder,
  useScheduleVersions,
} from '../../../../../_shared/hooks/useProjectSalesOrders';
import { useProject, usePurchaseOrders } from '../../../../../_shared/hooks/useProjects';
import type { AmendmentPreview } from '../../../../../_shared/types/projectSalesOrder.types';
import { AmendmentAutocountChangeList } from '../../../../components/AmendmentAutocountChangeList';
import { AmendmentCreateDialog } from '../../../../components/AmendmentCreateDialog';
import { AmendmentDeltaSummary } from '../../../../components/AmendmentDeltaSummary';
import { AmendmentDeltaTable } from '../../../../components/AmendmentDeltaTable';
import { AmendmentUnmatchedSection } from '../../../../components/AmendmentUnmatchedSection';
import { SalesOrderStatusPill } from '../../../../components/SalesOrderStatusPill';

const SCHEDULE_PREFIX = 'schedule:';
const PO_PREFIX = 'po:';

/**
 * The revision review.
 *
 * A newer PO or schedule version is uploaded elsewhere; here a person picks it and reads the
 * delta in purchasing's own verbs. Comparing writes nothing, which is why the compare step
 * and the create step are separate buttons rather than one.
 */
export function AmendmentReviewClient({
  projectId,
  psoId,
}: {
  projectId: string;
  psoId: string;
}) {
  const project = useProject(projectId);
  const salesOrder = useProjectSalesOrder(psoId);
  const purchaseOrders = usePurchaseOrders(projectId);

  const so = salesOrder.data;

  /**
   * The list row carries `po_number` but not always the PO's id, so the PO is resolved by
   * its number when the id is absent. Both are needed only to enumerate versions.
   */
  const poId =
    so?.purchase_order_id ||
    (purchaseOrders.data ?? []).find((po) => po.po_number && po.po_number === so?.po_number)?.id ||
    undefined;

  const scheduleVersions = useScheduleVersions(poId);
  const poVersions = usePoVersions(poId);
  const { preview, create, publish, updateRowDecisions } = useAmendmentMutations(
    projectId,
    psoId,
  );

  const [selection, setSelection] = React.useState('');
  const [result, setResult] = React.useState<AmendmentPreview | null>(null);
  const [creating, setCreating] = React.useState(false);

  /**
   * The amendment CREATE writes something the preview did not: from here on, decisions and
   * the change list address rows by `row_key`, which only exists once created. `create.data`
   * (rather than local state) is the source of the id, so it survives whatever the create
   * dialog does with its own "created" screen.
   */
  const amendmentId = create.data?.amendment_id ?? null;
  const amendment = useAmendment(amendmentId ?? undefined);
  const changeList = useAmendmentAutocountChangeList(amendmentId ?? undefined);
  const exportChangeList = useAmendmentAutocountChangeListExport(amendmentId ?? '');
  const published = amendment.data?.status === 'published';

  const options = React.useMemo(
    () => [
      ...(scheduleVersions.data ?? []).map((version) => ({
        value: `${SCHEDULE_PREFIX}${version.id}`,
        label: version.revision_label || `Version ${version.version_no}`,
        description: [
          version.issuer_party_label,
          version.schedule_date ? formatDateInMalaysia(version.schedule_date) : null,
        ]
          .filter(Boolean)
          .join(' · '),
        group: 'Delivery schedule versions',
      })),
      ...(poVersions.data ?? []).map((version) => ({
        value: `${PO_PREFIX}${version.id}`,
        label: `${version.po_number || 'PO'} version ${version.version_no}`,
        description: version.po_date ? formatDateInMalaysia(version.po_date) : undefined,
        group: 'Purchase order versions',
      })),
    ],
    [poVersions.data, scheduleVersions.data],
  );

  const compare = () => {
    if (!selection) return;
    const body = selection.startsWith(SCHEDULE_PREFIX)
      ? { schedule_version_id: selection.slice(SCHEDULE_PREFIX.length) }
      : { po_version_id: selection.slice(PO_PREFIX.length) };
    // mutate rather than mutateAsync: mutateAsync rethrows, and nothing here catches,
    // so a failed comparison escaped as an unhandled rejection and logged an uncaught
    // error in the browser even though the screen was already rendering the failure
    // from preview.isError. The error state is read off the mutation, so the throw was
    // never needed.
    preview.mutate(body, { onSuccess: setResult });
  };

  if (salesOrder.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (salesOrder.isError || !so) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This sales order could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {salesOrder.error instanceof Error
            ? salesOrder.error.message
            : 'It may have been rebuilt or deleted.'}
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href={`/project-sales/${projectId}?tab=sales-orders`}>Back to sales orders</Link>
        </Button>
      </div>
    );
  }

  const reference = so.autocount_doc_no || so.provisional_ref;
  const canEdit = project.data?.can_edit ?? false;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold break-words">{`Revision review: ${reference}`}</h1>
            <SalesOrderStatusPill status={so.status} />
          </div>
          <p className="mt-1 break-words text-sm text-muted-foreground">
            {[
              so.area_group || 'No area group',
              so.po_number ? `Customer PO ${so.po_number}` : 'No customer PO recorded',
            ].join(' · ')}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href={`/project-sales/${projectId}/sales-orders/${psoId}`}>
              Back to the draft
            </Link>
          </Button>
          {!amendmentId && result && canEdit && (
            <Button
              type="button"
              size="sm"
              disabled={result.rows.length === 0}
              onClick={() => setCreating(true)}
            >
              Create the amendment
            </Button>
          )}
          {amendmentId && canEdit && !published && (
            <Button
              type="button"
              size="sm"
              disabled={publish.isPending}
              onClick={() => publish.mutate(amendmentId)}
            >
              {publish.isPending ? 'Publishing…' : 'Publish the amendment'}
            </Button>
          )}
        </div>
      </div>

      {amendmentId ? (
        <AmendmentSection
          amendment={amendment}
          canEdit={canEdit}
          published={published}
          onDecide={(rowKey, decision, reason) =>
            updateRowDecisions.mutate({
              amendmentId,
              decisions: { [rowKey]: { decision, reason: reason ?? null } },
            })
          }
          changeList={changeList}
          exporting={exportChangeList.isPending}
          onExport={() => exportChangeList.mutate(reference)}
        />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Compare against</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <div className="w-full space-y-1.5 sm:w-80">
                  <Label htmlFor="revision-version">Newer version</Label>
                  {!poId ? (
                    <p className="rounded-md border border-dashed border-border px-3 py-2.5 text-sm text-muted-foreground">
                      This sales order is not linked to a purchase order we can read versions
                      from.
                    </p>
                  ) : scheduleVersions.isLoading || poVersions.isLoading ? (
                    <Skeleton className="h-9 w-full" />
                  ) : scheduleVersions.isError && poVersions.isError ? (
                    <p className="text-sm text-destructive">
                      {scheduleVersions.error instanceof Error
                        ? scheduleVersions.error.message
                        : 'The versions could not be loaded.'}
                    </p>
                  ) : options.length === 0 ? (
                    <p className="rounded-md border border-dashed border-border px-3 py-2.5 text-sm text-muted-foreground">
                      Only one version exists. Upload the revised PO or schedule on the project
                      first.
                    </p>
                  ) : (
                    <SearchableSelect
                      id="revision-version"
                      value={selection}
                      onChange={setSelection}
                      options={options}
                      placeholder="Select a version"
                    />
                  )}
                </div>
                <Button
                  type="button"
                  disabled={!selection || preview.isPending}
                  onClick={compare}
                >
                  <GitCompareArrows className="size-4" aria-hidden />
                  {preview.isPending ? 'Comparing…' : 'Compare'}
                </Button>
              </div>
            </CardContent>
          </Card>

          {preview.isPending ? (
            <div className="space-y-4">
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-64 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          ) : preview.isError && !result ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
              <h2 className="text-sm font-semibold text-destructive">
                The two versions could not be compared
              </h2>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                {preview.error instanceof Error ? preview.error.message : 'Try again shortly.'}
              </p>
            </div>
          ) : !result ? (
            <Card>
              <CardContent className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold">Nothing compared yet</h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  Pick the newer version above and press Compare. Nothing is written until you
                  create the amendment.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              <AmendmentDeltaSummary
                rows={result.rows}
                verbSummary={result.verb_summary ?? {}}
                unmatchedCount={(result.unmatched ?? []).length}
                fromLabel={result.from?.label || `version ${result.from?.version_no ?? ''}`}
                toLabel={result.to?.label || `version ${result.to?.version_no ?? ''}`}
              />
              <AmendmentDeltaTable rows={result.rows} />
              <AmendmentUnmatchedSection unmatched={result.unmatched ?? []} />
            </div>
          )}
        </>
      )}

      {creating && result && (
        <AmendmentCreateDialog
          preview={result}
          submitting={create.isPending}
          onDone={() => setCreating(false)}
          onConfirm={(reason) => {
            const body = selection.startsWith(SCHEDULE_PREFIX)
              ? { schedule_version_id: selection.slice(SCHEDULE_PREFIX.length), reason }
              : { po_version_id: selection.slice(PO_PREFIX.length), reason };
            return create.mutateAsync(body);
          }}
        />
      )}
    </div>
  );
}

/**
 * The created amendment: decisions and the AutoCount change list both need a `row_key` to
 * address, which only exists from here on - a bare preview has neither.
 */
function AmendmentSection({
  amendment,
  canEdit,
  published,
  onDecide,
  changeList,
  exporting,
  onExport,
}: {
  amendment: ReturnType<typeof useAmendment>;
  canEdit: boolean;
  published: boolean;
  onDecide: (rowKey: string, decision: 'accepted' | 'declined', reason?: string) => void;
  changeList: ReturnType<typeof useAmendmentAutocountChangeList>;
  exporting: boolean;
  onExport: () => void;
}) {
  if (amendment.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (amendment.isError || !amendment.data) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This amendment could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {amendment.error instanceof Error ? amendment.error.message : 'Try again shortly.'}
        </p>
      </div>
    );
  }

  const detail = amendment.data;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-sm">
            {detail.ocn_number ? `Change notice ${detail.ocn_number}` : 'Amendment'}
          </CardTitle>
          <Badge variant={published ? 'success' : 'secondary'} appearance="light">
            {(detail.status ?? 'proposed').replace(/_/g, ' ')}
          </Badge>
        </CardHeader>
        {detail.reason && (
          <CardContent>
            <p className="break-words text-sm text-muted-foreground">{detail.reason}</p>
          </CardContent>
        )}
      </Card>

      <AmendmentDeltaSummary
        rows={detail.rows}
        verbSummary={detail.verb_summary ?? {}}
        unmatchedCount={(detail.unmatched ?? []).length}
        fromLabel={detail.from?.label || `version ${detail.from?.version_no ?? ''}`}
        toLabel={detail.to?.label || `version ${detail.to?.version_no ?? ''}`}
      />
      <AmendmentDeltaTable rows={detail.rows} onDecide={onDecide} disabled={!canEdit || published} />
      <AmendmentAutocountChangeList
        rows={changeList.data?.rows ?? []}
        declinedCount={changeList.data?.declined_count ?? 0}
        isLoading={changeList.isLoading}
        exporting={exporting}
        onExport={onExport}
      />
      <AmendmentUnmatchedSection unmatched={detail.unmatched ?? []} />
    </div>
  );
}

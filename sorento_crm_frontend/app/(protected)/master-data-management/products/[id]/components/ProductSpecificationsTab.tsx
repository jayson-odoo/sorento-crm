'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { MoreVertical, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { readableEntry, valueLabelsByKey } from '@/lib/spec-readable';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { AddSpecificationDialog, SpecTable, type SpecKeyDefinition } from '@/components/spec-table';
import { usePermissions } from '@/hooks/usePermissions';
import { useProductSpecTable } from '../../hooks/useProductSpecTable';
import SpecExtractPanel from './SpecExtractPanel';
import { rederiveProduct } from '../../../product-specifications/services/productSpecService';
import type {
  ProductSpecDetail,
  SpecDiagnosisReason,
} from '../../../product-specifications/types/productSpec.types';
import type {
  VerificationBlock,
  VerificationState,
} from '../../../spec-verification/types/specVerification.types';

/**
 * What this product's specifications are, and where each one came from.
 *
 * Opened while looking at one product, so it answers the question asked there: is this
 * what the product actually is, and if not, put it right. Every value carries the
 * source it came from with the words behind it, because the only way to trust a
 * derived spec is to be able to see what it was derived from.
 *
 * The table itself is `components/spec-table`, props-driven and shared: the same
 * component renders here and, in milestone 2, inside the supplier portal. Everything
 * it needs comes from `useProductSpecTable`, so this file holds no fetching of its own
 * and the two surfaces cannot drift apart.
 */

/** Each silence gets its own sentence and its own fix. */
function diagnosisCopy(
  detail: ProductSpecDetail,
): { title: string; body: string; tone: 'warning' | 'destructive' } {
  const reason: SpecDiagnosisReason = detail.diagnosis.reason;
  const suffix = detail.diagnosis.suffix;

  switch (reason) {
    case 'class_not_enabled':
      return {
        tone: 'warning',
        title: `Product class "${suffix}" is not switched on yet`,
        body:
          `This product sits in category ${detail.category_code}. Spec derivation currently ` +
          'runs for Kitchen Sink only - the pilot class. Nothing about this product has ' +
          'been read, so a customer describing it will not find it. Widening the class ' +
          'list is what turns this on.',
      };
    case 'category_non_searchable':
      return {
        tone: 'warning',
        title: `Category ${detail.category_code} carries no product class`,
        body:
          'Codes like MISC, PROJECT, SRTPART and VD are deliberately marked ' +
          'non-searchable: they say nothing about what the product is, so guessing a ' +
          'class from them would hand the ranker its most damaging possible value.',
      };
    case 'code_unparsed':
      return {
        tone: 'destructive',
        title: `Category code ${detail.category_code} does not decompose`,
        body:
          'Codes are read as BRAND-CLASS. This one has no class half, so neither signal ' +
          'could be recovered. It needs either a corrected code or an explicit mapping.',
      };
    case 'no_category':
      return {
        tone: 'destructive',
        title: 'This product has no category',
        body:
          'Class is the single largest ranking signal and it comes from the category ' +
          'code. Without a category there is nothing to derive from.',
      };
    case 'not_yet_derived':
    default:
      return {
        tone: 'warning',
        title: 'Eligible, but nothing derived yet',
        body:
          `Class "${detail.diagnosis.class_label}" is switched on, so this product should ` +
          'have specs. The derivation job has not covered it - re-running derivation for ' +
          'this class will populate it.',
      };
  }
}

const VERIFICATION_LABEL: Record<VerificationState, string> = {
  verified: 'Verified',
  needs_reverify: 'Needs re-verify',
  unverified: 'Unverified',
};

/**
 * Whether a person has vouched for this product's specifications, and what moved since.
 *
 * Rendered whatever the state, next to the statuses in the header, because "nobody has
 * checked this yet" is an answer somebody came for as much as "verified". The pill is
 * the shared one, so a code reads the same here as it does in the worklist (AC-C.1).
 */
function VerificationStrip({
  block,
  registry,
  canEdit,
  busy,
  onVerify,
  onUnverify,
}: {
  block: VerificationBlock;
  registry: SpecKeyDefinition[];
  canEdit: boolean;
  busy: boolean;
  onVerify: () => void;
  onUnverify: () => void;
}) {
  const stamp =
    block.verified_by_name && block.verified_at
      ? `by ${block.verified_by_name}, ${formatDateTimeInMalaysia(block.verified_at)}`
      : null;
  // A withdrawal, as opposed to values moving under the stamp. Both facts are kept, so
  // the line names who took it back without losing who vouched for it (AC-D.20).
  const withdrawnBy =
    block.invalidated_reason === 'manual_unverify' && block.invalidated_by_name
      ? `Withdrawn by ${block.invalidated_by_name}${
          block.invalidated_at ? `, ${formatDateTimeInMalaysia(block.invalidated_at)}` : ''
        }`
      : null;
  const changed = block.state === 'needs_reverify' ? block.invalidated_diff?.changed ?? [] : [];
  const labelFor = (specKey: string) =>
    registry.find((key) => key.spec_key === specKey)?.label ?? specKey;
  const valueLabelsFor = (specKey: string) =>
    registry.find((key) => key.spec_key === specKey)?.value_labels;

  return (
    <div className="flex flex-col gap-2 rounded-md border p-3" data-spec-verification>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span
            className={`${STATUS_PILL_BASE} ${statusPillClass(block.state)}`}
            data-spec-verification-state
          >
            {VERIFICATION_LABEL[block.state]}
          </span>
          {stamp && <span className="text-sm text-muted-foreground">{stamp}</span>}
        </div>
        {canEdit && (
          <div className="flex flex-wrap items-center gap-2">
            {block.state === 'verified' ? (
              <Button size="sm" variant="outline" disabled={busy} onClick={onUnverify}>
                Unverify
              </Button>
            ) : (
              <Button size="sm" variant="outline" disabled={busy} onClick={onVerify}>
                Verify
              </Button>
            )}
          </div>
        )}
      </div>

      {withdrawnBy && <p className="text-sm text-muted-foreground">{withdrawnBy}</p>}

      {changed.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            What moved since it was verified
          </div>
          <ul className="flex flex-col gap-0.5">
            {changed.map((entry) => (
              <li key={entry.spec_key} className="text-sm break-words">
                <span className="font-medium">{labelFor(entry.spec_key)}</span>: was{' '}
                <span className="text-muted-foreground">
                  {readableEntry(entry.was, valueLabelsFor(entry.spec_key)) || 'nothing'}
                </span>
                , now{' '}
                <span className="font-medium">
                  {readableEntry(entry.now, valueLabelsFor(entry.spec_key)) || 'nothing'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function ProductSpecificationsTab({ productId }: { productId: string }) {
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  /** A key just picked from the dialog, so the table opens its editor on that row. */
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [confirmingUnverify, setConfirmingUnverify] = useState(false);
  const spec = useProductSpecTable(productId);
  const { detail, rows, registry, applicableKeys, otherKeys, heldKeys, isLoading, error } = spec;
  // `{spec_key: value_labels}` (E.2) - built once off the registry this tab already
  // loaded, so `SpecExtractPanel` needs no registry call of its own.
  const valueLabels = useMemo(() => valueLabelsByKey(registry), [registry]);

  // The server is the guard; these only decide what to SHOW. A user without the grant
  // gets no affordance that would 403 at submit - the same rule the dialog's own
  // denied state documents (AC-A.9). Slugs mirror the routes: the value writes need
  // products.edit, add-a-value takes either grant, creating a key needs the add grant.
  const { permissionSet } = usePermissions();
  const canEdit = permissionSet.has('master_data.products.edit');
  const canCreateKey = permissionSet.has('master_data.spec_registry.add');

  const rederive = async () => {
    setBusy(true);
    try {
      await rederiveProduct(productId);
      spec.refetch();
      toast.success('Read again with the current rules');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not read this product again', {
        duration: 10_000,
      });
    } finally {
      setBusy(false);
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex flex-col gap-2 pt-6">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertIcon />
        <AlertTitle>{error}</AlertTitle>
      </Alert>
    );
  }

  if (!detail) return null;

  const copy = detail.searchable ? null : diagnosisCopy(detail);
  // The row's own status, which the backend already computes with the same
  // precedence (needs_review > authored > derived). Read rather than recomputed.
  const specStatus = detail.spec?.status ?? 'derived';

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
          <CardTitle className="min-w-0 break-words">Specifications</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            {/* The shared pill, not a Badge variant: "findable" and "authored" are
                statuses, and a status that renders differently here than on every
                other screen is a second vocabulary to learn (AC-C.1). */}
            <span
              className={`${STATUS_PILL_BASE} ${statusPillClass(
                detail.searchable ? 'findable' : 'not_findable',
              )}`}
              data-spec-findability
            >
              {detail.searchable ? 'Findable by description' : 'Not findable by description'}
            </span>
            <span
              className={`${STATUS_PILL_BASE} ${statusPillClass(specStatus)}`}
              data-spec-status
            >
              {specStatus.replace(/_/g, ' ')}
            </span>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="Specification actions">
                  <MoreVertical className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={rederive} disabled={busy}>
                  <RefreshCw className="size-4" />
                  Read this product again
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          {/* Rendered in every state, verified or not (AC-D.13). It sits first because
              it is the question the worklist sent the reviewer here to answer. */}
          <VerificationStrip
            block={detail.verification}
            registry={registry}
            canEdit={canEdit}
            busy={spec.verificationBusy}
            onVerify={spec.verify}
            onUnverify={() => setConfirmingUnverify(true)}
          />

          {copy && (
            <Alert variant={copy.tone}>
              <AlertIcon />
              <div className="flex flex-col gap-1">
                <AlertTitle>{copy.title}</AlertTitle>
                <p className="text-sm">{copy.body}</p>
              </div>
            </Alert>
          )}

          <div className="flex flex-col gap-1.5">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Product description
            </div>
            <p className="rounded-md border bg-muted/30 p-3 font-mono text-sm break-words">
              {detail.source_text || '(no description)'}
            </p>
          </div>

          {/* Where the stored flyer card used to be, in the same place on the tab.
              The card was a copy of a printed document kept beside the values it
              produced and going stale against a flyer that had already been
              reprinted. This reads a text and proposes; nothing is stored but the
              values a person accepts. */}
          <SpecExtractPanel
            productId={productId}
            productCode={detail.product_code}
            canEdit={canEdit}
            valueLabels={valueLabels}
          />

          {detail.spec?.rendered_text && (
            <div className="flex flex-col gap-1.5">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                What search actually matches
              </div>
              <p className="rounded-md border p-3 text-sm break-words">
                {detail.spec.rendered_text}
              </p>
            </div>
          )}

          {/* Rendered unconditionally, empty or not (AC-A.14). Hiding the block on a
              product with no specs is what made "this product has none" and "this
              screen is broken" look identical, and it is the one thing a person
              arriving to ADD a specification most needs to see. */}
          <div className="flex flex-col gap-1.5">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Every value, and where it came from
            </div>
            <SpecTable
              rows={rows}
              registry={registry}
              canEdit={canEdit}
              openEditorFor={pendingKey}
              onEditorOpened={() => setPendingKey(null)}
              callbacks={{
                onSetValue: spec.setValue,
                onTombstone: spec.tombstone,
                onRevert: spec.revert,
                onAddValueToKey: canEdit ? spec.addValue : undefined,
                onAddSpecification: () => setAdding(true),
              }}
            />
          </div>
        </CardContent>
      </Card>

      <AddSpecificationDialog
        open={adding}
        onOpenChange={setAdding}
        applicableKeys={applicableKeys}
        otherKeys={otherKeys}
        heldKeys={heldKeys}
        canCreateKey={canCreateKey}
        // Picking a key opens its editor on the row rather than writing a blank value:
        // an empty value is not a value, and the API refuses one for the same reason -
        // stored, it would raise the same conflict on every derivation run forever.
        onPick={setPendingKey}
        onCreateKey={spec.createKey}
        onCheckSimilar={spec.checkSimilarKey}
      />

      <AlertDialog open={confirmingUnverify} onOpenChange={setConfirmingUnverify}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm unverify</AlertDialogTitle>
            <AlertDialogDescription>
              This withdraws the verification for {detail.product_code}. It reads Unverified
              again; the history keeps who vouched for it and who withdrew it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={spec.verificationBusy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                spec.unverify();
                setConfirmingUnverify(false);
              }}
              disabled={spec.verificationBusy}
            >
              Unverify
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <p className="text-sm text-muted-foreground">
        To try a customer phrase against the whole catalog, use{' '}
        <Link
          href="/master-data-management/product-specifications"
          className="underline underline-offset-2"
        >
          Product Specifications
        </Link>
        .
      </p>
    </div>
  );
}

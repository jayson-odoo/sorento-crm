'use client';

import { useState } from 'react';
import Link from 'next/link';
import { MoreVertical, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
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
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { AddSpecificationDialog, SpecTable } from '@/components/spec-table';
import { usePermissions } from '@/hooks/usePermissions';
import { useProductSpecTable } from '../../hooks/useProductSpecTable';
import SpecExtractPanel from './SpecExtractPanel';
import { rederiveProduct } from '../../../product-specifications/services/productSpecService';
import type {
  ProductSpecDetail,
  SpecDiagnosisReason,
} from '../../../product-specifications/types/productSpec.types';

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

const EXCEPTION_LABELS: Record<string, string> = {
  shape_mismatch: 'Stored dimensions describe a round or square product',
  column_conflict: 'Description disagrees with the stored dimensions',
  implausible_dimension: 'Dimension too large to be real',
  low_confidence: 'Derived below the review threshold',
  // An authored value the rules now disagree with. Setting the right value is what
  // answers it - there is deliberately no resolve action anywhere on this page (D9).
  human_override_conflict: 'The rules read something else than the value set by hand',
};

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
          'runs for Kitchen Sink only — the pilot class. Nothing about this product has ' +
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
          'have specs. The derivation job has not covered it — re-running derivation for ' +
          'this class will populate it.',
      };
  }
}

export default function ProductSpecificationsTab({ productId }: { productId: string }) {
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  /** A key just picked from the dialog, so the table opens its editor on that row. */
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const spec = useProductSpecTable(productId);
  const { detail, rows, registry, applicableKeys, otherKeys, heldKeys, isLoading, error } = spec;

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

      {/* Rendered whether or not there are any, per the never-hide-a-section mandate -
          "nothing disagrees" is the answer a reviewer came for. */}
      <Card>
        <CardHeader>
          <CardTitle>Needs a human ({detail.exceptions.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {detail.exceptions.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Nothing on this product disagrees with itself.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {detail.exceptions.map((row) => (
                <div
                  key={row.id}
                  className="flex flex-col gap-1 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium">
                      {registry.find((key) => key.spec_key === row.spec_key)?.label ??
                        row.spec_key}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {EXCEPTION_LABELS[row.reason] ?? row.reason}
                    </div>
                  </div>
                  {/* No resolve button anywhere here, on purpose (D9). Correcting the
                      value in the table above is what answers it, and a button that
                      only marked it read would be a second source of truth about
                      whether the catalogue is right. */}
                  <div className="text-sm text-muted-foreground">
                    The rules read{' '}
                    <span className="font-medium text-foreground">
                      {String((row.proposed as { value?: unknown })?.value ?? '')}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

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

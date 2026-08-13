'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { MoreVertical, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  clearSpecValueByHand,
  getProductSpecDetail,
  rederiveProduct,
  setFlyerText,
} from '../../../product-specifications/services/productSpecService';
import { readable, readableValue } from '../../../product-specifications/lib/readable';
import AddSpecByHand from './AddSpecByHand';
import type {
  ProductSpecDetail,
  SpecDiagnosisReason,
} from '../../../product-specifications/types/productSpec.types';

/**
 * What the machine read out of THIS product, and what search will do with it.
 *
 * Opened while looking at one product, so it answers the question asked there: can a
 * customer find this by describing it, and if not, what is stopping it. Every value
 * carries the exact substring it came from, because the only way to trust a derived
 * spec is to see the words it was derived from sitting next to it.
 */

/** Where a value came from, named the way the person reading it would name it. */
const SOURCE_LABEL: Record<string, string> = {
  derived: 'Description',
  flyer: 'Flyer',
  code: 'Product code',
  category: 'Category',
  human: 'Set by hand',
};

const EXCEPTION_LABELS: Record<string, string> = {
  shape_mismatch: 'Stored dimensions describe a round or square product',
  column_conflict: 'Description disagrees with the stored dimensions',
  implausible_dimension: 'Dimension too large to be real',
  low_confidence: 'Derived below the review threshold',
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

/**
 * The flyer card this product's specs are read from, correctable in place.
 *
 * The card text is a machine reading of the printed flyer and it is not complete — a
 * card split across a column break, or one whose code the reading could not place,
 * leaves the product with no dimensions, no seat material, no flush type and nothing on
 * screen explaining the hole. Correcting it here re-reads the product on save, so the
 * specs move in the same click.
 */
function FlyerCard({
  productId,
  text,
  onSaved,
}: {
  productId: string;
  text: string | null;
  onSaved: () => Promise<void> | void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(text ?? '');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await setFlyerText(productId, draft);
      toast.success('Flyer card saved', { description: 'This product was read again.' });
      setEditing(false);
      await onSaved();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save the flyer text', {
        duration: 10_000,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Flyer card for this code
        </div>
        {!editing && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setDraft(text ?? '');
              setEditing(true);
            }}
          >
            {text ? 'Edit' : 'Add the card text'}
          </Button>
        )}
      </div>

      {editing ? (
        <div className="flex flex-col gap-2">
          <textarea
            className="min-h-[6rem] w-full rounded-md border border-input bg-background p-3 font-mono text-sm"
            value={draft}
            placeholder="e.g. Washdown With Rimless. D: L680xW375xH770mm. *PP Seat Cover"
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save and read again'}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEditing(false)}
              disabled={saving}
            >
              Cancel
            </Button>
            <span className="text-xs text-muted-foreground">
              Emptying the box means this product has no flyer card.
            </span>
          </div>
        </div>
      ) : text ? (
        <p className="rounded-md border bg-muted/30 p-3 font-mono text-sm break-words whitespace-pre-wrap">
          {text}
        </p>
      ) : (
        <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          No flyer card for this code. Anything the flyer prints but the description does
          not — dimensions, seat material, flush type — cannot be read until one is here.
        </p>
      )}
    </div>
  );
}

export default function ProductSpecificationsTab({ productId }: { productId: string }) {
  const [detail, setDetail] = useState<ProductSpecDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setDetail(await getProductSpecDetail(productId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const rederive = async () => {
    setBusy(true);
    try {
      await rederiveProduct(productId);
      await load();
      toast.success('Read again with the current rules');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not read this product again', {
        duration: 10_000,
      });
    } finally {
      setBusy(false);
    }
  };

  const clearByHand = async (key: string) => {
    try {
      await clearSpecValueByHand(productId, key);
      await load();
      toast.success(`${readable(key)} is back to what the rules read`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not clear the value');
    }
  };

  if (loading) {
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

  const values = detail.spec?.values ?? {};
  const provenance = detail.spec?.provenance ?? {};
  const entries = Object.entries(values).sort(([a], [b]) => a.localeCompare(b));
  const copy = detail.searchable ? null : diagnosisCopy(detail);

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Derived specifications</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            {detail.searchable ? (
              <Badge variant="success" size="sm">
                Findable by description
              </Badge>
            ) : (
              <Badge variant="secondary" size="sm">
                Not findable by description
              </Badge>
            )}
            {detail.spec?.status && (
              <Badge variant="outline" size="sm">
                {detail.spec.status.replace(/_/g, ' ')}
              </Badge>
            )}
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
                <DropdownMenuItem onClick={() => setAdding(true)}>
                  <Plus className="size-4" />
                  Set a value by hand
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          {adding && (
            <AddSpecByHand
              productId={productId}
              onCancel={() => setAdding(false)}
              onSaved={() => {
                setAdding(false);
                load();
              }}
            />
          )}

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

          {/* The second text. A value marked Flyer was read from here and appears
              nowhere on the product master, so without it there is no way to check it.
              Editable, and shown even when empty: the flyer reading missed cards, and a
              product with no card silently loses its dimensions with nothing on screen
              to say why or to put it right. */}
          <FlyerCard
            productId={productId}
            text={detail.flyer_text}
            onSaved={load}
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

          {entries.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                Every value, and the text it was read from
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                      <th className="pb-2 pr-4">Spec</th>
                      <th className="pb-2 pr-4">Value</th>
                      <th className="pb-2 pr-4">Read from</th>
                      <th className="pb-2">Words it was read from</th>
                      <th className="pb-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map(([key, value]) => (
                      <tr key={key} className="border-b last:border-0">
                        <td className="py-2 pr-4 whitespace-nowrap">{readable(key)}</td>
                        <td className="py-2 pr-4 whitespace-nowrap">
                          {readableValue(value.value, value.unit)}
                        </td>
                        <td className="py-2 pr-4 whitespace-nowrap">
                          {provenance[key]?.source ? (
                            <Badge
                              variant={provenance[key]?.source === 'flyer' ? 'info' : 'secondary'}
                              size="sm"
                              appearance="light"
                              shape="circle"
                            >
                              {SOURCE_LABEL[provenance[key]!.source] ?? provenance[key]!.source}
                            </Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="py-2 font-mono text-xs text-muted-foreground break-all">
                          {provenance[key]?.evidence ?? '-'}
                        </td>
                        <td className="py-2 text-right">
                          {provenance[key]?.source === 'human' && (
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Clear ${readable(key)}`}
                              onClick={() => clearByHand(key)}
                            >
                              <Trash2 className="size-4 text-muted-foreground" />
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {detail.exceptions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Needs a human ({detail.exceptions.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-4">Spec</th>
                    <th className="pb-2 pr-4">Why</th>
                    <th className="pb-2">Stored</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.exceptions.map((row) => (
                    <tr key={row.id} className="border-b last:border-0">
                      <td className="py-2 pr-4">{row.spec_key}</td>
                      <td className="py-2 pr-4">
                        {EXCEPTION_LABELS[row.reason] ?? row.reason}
                      </td>
                      <td className="py-2 font-mono text-xs text-muted-foreground">
                        {row.stored ? JSON.stringify(row.stored) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

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

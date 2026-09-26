'use client';

import { useMemo, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { DeferredCountdown } from '@/components/common/DeferredActionButton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { readableEntry, readableValue } from '@/lib/spec-readable';
import {
  AddSpecificationDialog,
  SpecTable,
  type SpecKeyDefinition,
  type SpecTableRow,
} from '@/components/spec-table';
import { usePermissions } from '@/hooks/usePermissions';
import { useProductSpecTable } from '../../hooks/useProductSpecTable';
import { useProduct, useUpdateProduct } from '../../hooks/useProducts';
import { previewSpecSearch } from '../../../product-specifications/services/productSpecService';
import { InsertFieldDialog } from '@/app/(protected)/dealer-kit/tag-templates/components/InsertFieldDialog';
import {
  hasMergeField,
  mergeFieldCatalog,
  renderPriceTagDescription,
  type MergeFieldGroup,
  type SpecKeyOption,
} from '@/lib/dealer-kit/merge-fields';
import type { TagBindingData } from '@/lib/dealer-kit/tag-template-types';
import type { VerificationBlock } from '../../../spec-verification/types/specVerification.types';

// AC-S4-11: this product's own description cannot address a line, a set or a
// combo part - only its own fields and its own specs.
const PRICE_TAG_INSERT_GROUPS: MergeFieldGroup[] = ['Product', 'Specs'];

const UNDO_WINDOW_SECONDS = 5;

/**
 * What this product's specifications are, and where each one came from.
 *
 * Opened while looking at one product, so it answers the question asked there: is this
 * what the product actually is, and if not, put it right. Order, top to bottom
 * (AC-S2.1): the checked line, the values table, the price tag wording, then a
 * plain Reading and search section - two things only, always shown (D9, owner
 * ruling 27 Sep 2026, "simplify this, too messy"). Every value carries the source
 * it came from, so the only way to trust a derived spec is to be able to see what
 * it was derived from; a value read off the product's own record never claims to
 * be a read of the description (AC-S2.7).
 *
 * The table itself is `components/spec-table`, props-driven and shared: the same
 * component renders here and, in milestone 2, inside the supplier portal. Everything
 * it needs comes from `useProductSpecTable`, so this file holds no fetching of its own
 * and the two surfaces cannot drift apart.
 */

function ordinal(n: number): string {
  const suffixes = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return `${n}${suffixes[(v - 20) % 10] ?? suffixes[v] ?? suffixes[0]}`;
}

/**
 * "Not checked yet" / "Checked by {name} on {date}" / "Needs checking again"
 * (AC-S2.3). Undo is a deferred 5s action, never a confirm dialog (AC-S2.4) - a
 * purely client-side countdown that calls the real `unverify()` only once it
 * lapses, so the record stays Checked until the window actually closes.
 */
function CheckedLine({
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
  const [undo, setUndo] = useState<{ commitAt: number; timer: ReturnType<typeof setTimeout> } | null>(
    null,
  );

  const stamp =
    block.verified_by_name && block.verified_at
      ? `Checked by ${block.verified_by_name} on ${formatDateTimeInMalaysia(block.verified_at)}`
      : null;
  const withdrawnBy =
    block.invalidated_reason === 'manual_unverify' && block.invalidated_by_name
      ? `Withdrawn by ${block.invalidated_by_name}${
          block.invalidated_at ? `, ${formatDateTimeInMalaysia(block.invalidated_at)}` : ''
        }`
      : null;
  const changed = block.state === 'needs_reverify' ? block.invalidated_diff?.changed ?? [] : [];
  const labelFor = (specKey: string) => registry.find((key) => key.spec_key === specKey)?.label ?? specKey;
  const valueLabelsFor = (specKey: string) =>
    registry.find((key) => key.spec_key === specKey)?.value_labels;

  const startUndo = () => {
    const commitAt = Date.now() + UNDO_WINDOW_SECONDS * 1000;
    const timer = setTimeout(() => {
      onUnverify();
      setUndo(null);
    }, UNDO_WINDOW_SECONDS * 1000);
    setUndo({ commitAt, timer });
  };
  const cancelUndo = () => {
    if (undo) clearTimeout(undo.timer);
    setUndo(null);
  };

  const line =
    block.state === 'verified'
      ? stamp
      : block.state === 'needs_reverify'
        ? 'Needs checking again'
        : 'Not checked yet';

  return (
    <div className="flex flex-col gap-2 rounded-md border p-3" data-spec-verification>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-sm font-medium" data-spec-verification-state>
            {line}
          </span>
        </div>
        {canEdit && !undo && (
          <div className="flex flex-wrap items-center gap-2">
            {block.state === 'verified' ? (
              <Button size="sm" variant="outline" disabled={busy} onClick={startUndo}>
                Undo
              </Button>
            ) : (
              <Button size="sm" variant="outline" disabled={busy} onClick={onVerify}>
                Mark as checked
              </Button>
            )}
          </div>
        )}
        {undo && (
          <DeferredCountdown
            pending={{
              id: 'spec-verification-undo',
              action_key: 'spec_verification.undo',
              entity_type: 'spec_verification',
              entity_id: 'this-product',
              commit_at: new Date(undo.commitAt).toISOString(),
              window_seconds: UNDO_WINDOW_SECONDS,
            }}
            verb="Undoing"
            onCancel={cancelUndo}
          />
        )}
      </div>

      {withdrawnBy && <p className="text-sm text-muted-foreground">{withdrawnBy}</p>}

      {changed.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            What moved since it was checked
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

/**
 * "Price tag description" (S11, amends S4): a per-product TEMPLATE, edited
 * in place, with the same Insert field picker the tag template designer
 * uses and a live "Prints as:" preview - so the person writing it sees the
 * exact words a customer will read, before it is ever saved.
 */
function PriceTagDescriptionBlock({
  productId,
  storedTemplate,
  canEdit,
  rows,
  registry,
  productCode,
  productName,
  listPrice,
}: {
  productId: string;
  storedTemplate: string | null;
  canEdit: boolean;
  rows: SpecTableRow[];
  registry: SpecKeyDefinition[];
  productCode: string;
  productName: string;
  listPrice: number | null;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [insertOpen, setInsertOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { mutateAsync, isPending } = useUpdateProduct();

  const specKeys: SpecKeyOption[] = useMemo(
    () => registry.map((key) => ({ key: key.spec_key, label: key.label, unit: key.unit })),
    [registry],
  );

  // This product's own spec values, in the SAME readable form the table
  // itself renders through (`readableValue`) - never the raw stored slug
  // (AC-S4-12).
  const previewBinding: TagBindingData = useMemo(
    () => ({
      kind: 'product',
      product: {
        id: productId,
        code: productCode,
        name: productName,
        dimensions: '',
        spec_lines: [],
        specs: rows.map((row) => ({
          key: row.specKey,
          label: row.label,
          value: readableValue(row.value, row.unit ?? undefined, row.valueLabels),
          unit: row.unit,
        })),
        images: [],
        list_price: listPrice,
        offer_price: null,
        promotion_id: null,
        barcode: null,
      },
    }),
    [productId, productCode, productName, listPrice, rows],
  );

  const activeText = editing ? draft : storedTemplate ?? '';
  const printsAs = renderPriceTagDescription(activeText, previewBinding, 'print');

  // AC-S4-18: "known" is the SAME restricted catalog Insert field offers -
  // a token this product simply carries no VALUE for is not "unknown", only
  // a path the catalog does not name at all is.
  const knownPaths = useMemo(
    () => new Set(mergeFieldCatalog(specKeys, PRICE_TAG_INSERT_GROUPS).map((field) => field.path)),
    [specKeys],
  );
  const unknownTokens = useMemo(() => {
    const seen = new Set<string>();
    const tokens: string[] = [];
    for (const match of activeText.matchAll(/\{\{\s*([A-Za-z0-9_.]+)\s*\}\}/g)) {
      const path = match[1];
      if (knownPaths.has(path) || seen.has(path)) continue;
      seen.add(path);
      tokens.push(`{{${path}}}`);
    }
    return tokens;
  }, [activeText, knownPaths]);

  const startEdit = () => {
    setDraft(storedTemplate ?? '');
    setEditing(true);
  };
  const cancelEdit = () => setEditing(false);
  const save = async () => {
    await mutateAsync({ id: productId, data: { price_tag_description: draft } });
    setEditing(false);
  };

  const insertAtCaret = (content: string) => {
    setDraft(content);
    setInsertOpen(false);
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        Price tag description
      </div>

      {editing ? (
        <div className="flex flex-col gap-2">
          <Textarea
            ref={textareaRef}
            aria-label="Price tag description"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') cancelEdit();
            }}
            rows={3}
            className="font-mono text-sm"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setInsertOpen(true)}>
              Insert field
            </Button>
            <Button size="sm" onClick={save} disabled={isPending}>
              Save
            </Button>
            <Button size="sm" variant="ghost" onClick={cancelEdit} disabled={isPending}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="rounded-md border bg-muted/30 p-3 font-mono text-sm whitespace-pre-line break-words">
            {storedTemplate || 'Not set, the price tag uses the product description'}
          </p>
          {canEdit && (
            <div>
              <Button size="sm" variant="outline" onClick={startEdit}>
                Edit price tag description
              </Button>
            </div>
          )}
        </div>
      )}

      {hasMergeField(activeText) && (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Prints as:</span>
          <p className="text-sm whitespace-pre-line break-words">{printsAs}</p>
          {unknownTokens.length > 0 && (
            <p className="text-destructive text-xs">Unknown field: {unknownTokens.join(', ')}</p>
          )}
        </div>
      )}

      <InsertFieldDialog
        open={insertOpen}
        value={draft}
        data={previewBinding}
        specKeys={specKeys}
        groups={PRICE_TAG_INSERT_GROUPS}
        onCancel={() => setInsertOpen(false)}
        onDone={insertAtCaret}
      />
    </div>
  );
}

/**
 * "Reading and search" (AC-S2.1, AC-S2.5, D9): the read values line and one
 * search box, nothing else. No "Read this product again" - the product is read
 * again by itself whenever its code, description, category, sizes or flyer
 * change (AC-S2.9).
 */
function ReadingAndSearch({ productId, renderedText }: { productId: string; renderedText: string | null }) {
  const [phrase, setPhrase] = useState('');
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    const trimmed = phrase.trim();
    if (!trimmed) {
      setAnswer(null);
      return;
    }
    setLoading(true);
    try {
      const terms = trimmed.split(/\s+/);
      const result = await previewSpecSearch({
        specs: [],
        free_terms: [trimmed, ...terms],
        phrase: trimmed,
        understand: true,
      });
      const place = result.candidates.findIndex((c) => c.product_id === productId);
      setAnswer(
        place >= 0
          ? `This product comes up, ${ordinal(place + 1)} of ${result.candidates.length}`
          : 'This product does not come up for this',
      );
    } catch {
      setAnswer('Could not run that search');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-md border p-4">
      <h3 className="text-sm font-semibold">Reading and search</h3>

      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">Read values</span>
        <p className="text-sm break-words">{renderedText || 'Nothing read yet.'}</p>
      </div>

      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">Search</span>
        <div className="flex items-center gap-2">
          <div className="relative min-w-0 flex-1 max-w-md">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              className="pl-8"
              value={phrase}
              placeholder="Type what a customer would ask"
              onChange={(e) => setPhrase(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void run();
              }}
            />
          </div>
        </div>
        {loading && <p className="text-sm text-muted-foreground">Searching...</p>}
        {!loading && answer && <p className="text-sm font-medium">{answer}</p>}
      </div>
    </div>
  );
}

export default function ProductSpecificationsTab({ productId }: { productId: string }) {
  const [adding, setAdding] = useState(false);
  /** A key just picked from the dialog, so the table opens its editor on that row. */
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const spec = useProductSpecTable(productId);
  const { detail, rows, registry, applicableKeys, otherKeys, heldKeys, isLoading, error } = spec;
  // Same `['product', id]` query `ProductDetail.tsx` already populates when it
  // mounts this tab (S11) - no second round trip on the page's own first paint.
  const { data: product } = useProduct(productId);

  // The server is the guard; these only decide what to SHOW. A user without the grant
  // gets no affordance that would 403 at submit.
  const { permissionSet } = usePermissions();
  const canEdit = permissionSet.has('master_data.products.edit');

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
      <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (!detail) return null;

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader>
          <CardTitle className="min-w-0 break-words">Specifications</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          {/* Rendered in every state (AC-S2.1): the checked line is the question a
              merchandiser came here to answer, so it sits first. */}
          <CheckedLine
            block={detail.verification}
            registry={registry}
            canEdit={canEdit}
            busy={spec.verificationBusy}
            onVerify={spec.verify}
            onUnverify={spec.unverify}
          />

          {/* Rendered unconditionally, empty or not: hiding this on a product with
              no specs is what made "this product has none" and "this screen is
              broken" look identical. */}
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

          <PriceTagDescriptionBlock
            productId={productId}
            storedTemplate={product?.price_tag_description ?? null}
            canEdit={canEdit}
            rows={rows}
            registry={registry}
            productCode={product?.product_code ?? detail.product_code}
            productName={product?.product_name ?? ''}
            listPrice={product?.list_price ?? null}
          />

          <ReadingAndSearch productId={productId} renderedText={detail.spec?.rendered_text ?? null} />
        </CardContent>
      </Card>

      <AddSpecificationDialog
        open={adding}
        onOpenChange={setAdding}
        applicableKeys={applicableKeys}
        otherKeys={otherKeys}
        heldKeys={heldKeys}
        canCreateKey={permissionSet.has('master_data.spec_registry.add')}
        // Picking a key opens its editor on the row rather than writing a blank value:
        // an empty value is not a value, and the API refuses one for the same reason -
        // stored, it would raise the same conflict on every derivation run forever.
        onPick={setPendingKey}
        onCreateKey={spec.createKey}
        onCheckSimilar={spec.checkSimilarKey}
      />
    </div>
  );
}

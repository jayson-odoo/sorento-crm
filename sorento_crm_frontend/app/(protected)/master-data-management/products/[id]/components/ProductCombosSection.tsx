'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import { ImagePlus, LoaderCircleIcon, Pencil, Plus, Trash2, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NumberInput } from '@/components/ui/number-input';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import AttachmentPreviewModal from '@/components/common/AttachmentPreviewModal';
import { RichTextView } from '@/components/dealer-kit/RichTextView';
import { toEditorHtml } from '@/lib/dealer-kit/rich-text';
import { numberFieldError } from '@/lib/number-field';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  useAddProductComboPart,
  useProductComboDelete,
  useProductComboPartDelete,
  useProductCombos,
  useUpdateProductCombo,
  useUpdateProductComboPart,
} from '../../hooks/useProductCombos';
import { useProductComboImage } from '../../hooks/useProductComboImage';
import { getProducts } from '../../services/productService';
import type {
  ProductComboPartRow,
  ProductComboPartUpdate,
  ProductComboRow,
  ProductComboUpdate,
} from '../../types/productCombo.types';
import { COMBO_NAME_MAX } from '../../types/productCombo.types';
import { AddComboModal } from './AddComboModal';
import { ComboTagPreview } from './ComboTagPreview';
import { ComboTemplatesField } from './ComboTemplatesField';
import { AccessoryListField } from './AccessoryListField';
import { codeWithName, distinctName } from '@/lib/product-display';

/** Server-searched and PAGED, never one cached page: the catalogue is 22,000 rows. */
const PRODUCT_PAGE_SIZE = 50;

async function fetchProductOptions(
  query: string,
  pageIndex: number,
): Promise<SearchableSelectOption[]> {
  const products = await getProducts({
    pageIndex,
    pageSize: PRODUCT_PAGE_SIZE,
    sorting: [],
    searchQuery: query,
    status: 'active',
  });
  return (products.data ?? []).map((product) => ({
    value: product.id,
    label: codeWithName(product.product_code, product.product_name),
    searchText: `${product.product_code} ${product.product_name}`,
  }));
}

/** A Decimal arrives as a string ("2500.00"); the box wants a number. */
function toNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatMoney(value: number | string | null | undefined): string {
  const amount = toNumber(value);
  return amount === null
    ? '-'
    : `RM ${amount.toLocaleString('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * A money box that saves on blur, and only when the figure changed. Empty saves null
 * (the price goes back to the summed one); a draft that is not a number, or is negative,
 * shows its message and is not saved.
 */
function MoneyField({
  id,
  label,
  ariaLabel,
  value,
  onSave,
  className,
  labelClassName,
}: {
  id: string;
  label: string;
  /** Names the input through its row when the visible label alone would be ambiguous. */
  ariaLabel?: string;
  value: number | string | null | undefined;
  /** `revert` puts the box back to the saved figure when the server refuses the write. */
  onSave: (next: number | null, revert: () => void) => void;
  className?: string;
  labelClassName?: string;
}) {
  const saved = toNumber(value);
  const [draft, setDraft] = useState<number | null>(saved);
  const [touched, setTouched] = useState(false);
  const error = numberFieldError(draft, { min: 0, optional: true });
  return (
    <div className={className}>
      <Label htmlFor={id} className={labelClassName}>
        {label}
      </Label>
      <NumberInput
        id={id}
        aria-label={ariaLabel}
        min={0}
        step="0.01"
        inputMode="decimal"
        value={draft}
        onValueChange={setDraft}
        error={touched ? error : undefined}
        onBlur={() => {
          setTouched(true);
          if (error) return;
          if (draft !== saved) onSave(draft, () => setDraft(saved));
        }}
      />
    </div>
  );
}

/**
 * The combo description in the shared rich text editor, with the tag it prints on drawn beside it.
 * Saves on blur (when focus leaves the editor, toolbar included) and only when the text changed; a
 * refused save puts the saved text back. Empty saves null. The preview follows the draft.
 */
function DescriptionField({
  combo,
  onSave,
}: {
  combo: ProductComboRow;
  onSave: (next: string | null, revert: () => void) => void;
}) {
  const saved = combo.description ?? '';
  const [draft, setDraft] = useState(saved);
  const labelId = `${combo.id}-description-label`;
  const commit = (event: React.FocusEvent<HTMLElement>) => {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    if (draft !== saved) onSave(draft.trim() === '' ? null : draft, () => setDraft(saved));
  };
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div className="min-w-0 space-y-1.5">
        <Label id={labelId}>Description</Label>
        <div onBlur={commit}>
          <RichTextEditor
            aria-labelledby={labelId}
            value={toEditorHtml(draft)}
            onChange={setDraft}
            minHeight={140}
          />
        </div>
      </div>
      <div className="min-w-0">
        <ComboTagPreview combo={combo} description={draft.trim() === '' ? null : draft} />
      </div>
    </div>
  );
}

/**
 * The combo's name, renamed in place (COMBO-RENAME): a pencil swaps the title for an input
 * with Save and Cancel, the same shape as the Family code edit on the Variants tab
 * (`ProductVariantsTab.tsx`). Enter saves, Escape cancels. The refusals are answered under the
 * input, where the name that has to change is.
 */
function ComboNameField({
  name,
  canEdit,
  onRename,
}: {
  name: string;
  canEdit: boolean;
  /** Resolves once saved, rejects with the refusal (`status` set when the server answered). */
  onRename: (next: string) => Promise<unknown>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const start = () => {
    setDraft(name);
    setError(null);
    setEditing(true);
  };
  const cancel = () => {
    setEditing(false);
    setError(null);
  };
  const save = async () => {
    const next = draft.trim();
    if (!next) {
      setError('A combo needs a name');
      return;
    }
    if (next === name) {
      cancel();
      return;
    }
    setError(null);
    setSaving(true);
    // Awaited rather than per-call callbacks: the section shares one update mutation with the
    // price and description edits, and a later `mutate` drops an earlier call's callbacks.
    try {
      await onRename(next);
      setEditing(false);
    } catch (caught) {
      const failure = caught as Error & { status?: number };
      setError(
        failure.status === 409
          ? 'Another combo on this product already has this name'
          : failure.message || 'Failed to rename the combo',
      );
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <div className="flex min-w-0 items-center gap-1">
        <p className="min-w-0 truncate font-medium" title={name}>
          {name}
        </p>
        {canEdit ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="shrink-0"
            onClick={start}
            aria-label={`Rename combo ${name}`}
          >
            <Pencil className="size-4" />
          </Button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="min-w-0 flex-1 space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="Combo name"
          className="min-w-0 flex-1 sm:max-w-md"
          value={draft}
          maxLength={COMBO_NAME_MAX}
          autoFocus
          disabled={saving}
          aria-invalid={error ? true : undefined}
          onChange={(event) => {
            setDraft(event.target.value);
            if (error) setError(null);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              void save();
            } else if (event.key === 'Escape') {
              event.preventDefault();
              cancel();
            }
          }}
        />
        <Button type="button" size="sm" onClick={() => void save()} disabled={saving}>
          Save
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={cancel} disabled={saving}>
          Cancel
        </Button>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}

/** Label and value as text, for a reader without the edit permission. */
function ReadOnlyField({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="min-w-0 space-y-0.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="whitespace-pre-line break-words text-sm">{value || '-'}</p>
    </div>
  );
}

interface PartRowProps {
  part: ProductComboPartRow;
  groupOptions: SearchableSelectOption[];
  canEdit: boolean;
  isRemoving: boolean;
  onChoiceGroup: (label: string | null) => void;
  onWrite: (write: ProductComboPartUpdate, revert?: () => void) => void;
  onRemove: () => void;
}

function PartRow({
  part,
  groupOptions,
  canEdit,
  isRemoving,
  onChoiceGroup,
  onWrite,
  onRemove,
}: PartRowProps) {
  const isOption = !!part.choice_group && !part.is_upgrade;
  return (
    <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_13rem_auto] sm:items-center">
      <div className="min-w-0">
        <p className="truncate font-medium" title={part.code}>
          {part.code}
        </p>
        {distinctName(part.code, part.product_name) ? (
          <p className="truncate text-sm text-muted-foreground" title={part.product_name}>
            {part.product_name}
          </p>
        ) : null}
        <p className="truncate text-xs text-muted-foreground">{part.dimensions || '-'}</p>
      </div>
      {canEdit ? (
        <SearchableSelect
          clearable
          truncateTriggerLabel
          value={part.choice_group ?? ''}
          onChange={(value) => onChoiceGroup(value || null)}
          options={groupOptions}
          placeholder="Fixed part"
          emptyMessage="No choice groups yet."
          // The vocabulary is whatever marketing already called a group on THIS
          // combo, plus whatever they type now - a basin group is a word off the
          // catalogue page, not a list the system can know in advance.
          createOption={{
            label: (query) => {
              const trimmed = query.trim();
              // Nothing to create when the label already exists on this combo:
              // the row above it IS that group, and offering both reads as two
              // different answers to the same word.
              if (
                !trimmed ||
                groupOptions.some((opt) => opt.value.toLowerCase() === trimmed.toLowerCase())
              ) {
                return null;
              }
              return `Use "${trimmed}"`;
            },
            onCreate: (query) => onChoiceGroup(query.trim() || null),
          }}
          disabled={isRemoving}
        />
      ) : (
        <p className="text-sm text-muted-foreground">{part.choice_group || 'Fixed part'}</p>
      )}
      {canEdit ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="justify-self-start sm:justify-self-end"
          onClick={onRemove}
          disabled={isRemoving}
          aria-label={`Remove ${part.code}`}
        >
          {isRemoving ? (
            <LoaderCircleIcon className="size-4 animate-spin" />
          ) : (
            <Trash2 className="size-4 text-destructive" />
          )}
        </Button>
      ) : null}
      {canEdit ? (
        <div className="flex flex-wrap items-end gap-3 sm:col-span-full">
          {isOption ? (
            <MoneyField
              id={`${part.id}-sell`}
              label="Sell price if picked"
              ariaLabel={`Sell price if picked for ${part.code}`}
              value={part.sell_price}
              onSave={(next, revert) => onWrite({ sell_price: next }, revert)}
              className="w-40 space-y-1.5"
              labelClassName="text-xs text-muted-foreground"
            />
          ) : null}
          {part.is_upgrade ? (
            <MoneyField
              id={`${part.id}-topup`}
              label="Top-up"
              ariaLabel={`Top-up for ${part.code}`}
              value={part.topup_amount}
              onSave={(next, revert) => onWrite({ topup_amount: next }, revert)}
              className="w-40 space-y-1.5"
              labelClassName="text-xs text-muted-foreground"
            />
          ) : null}
          <label className="flex items-center gap-2 pb-2 text-sm">
            <Checkbox
              checked={!!part.is_upgrade}
              onCheckedChange={(checked) => onWrite({ is_upgrade: checked === true })}
              disabled={isRemoving}
            />
            <span>Upgrade</span>
          </label>
        </div>
      ) : (
        <div className="sm:col-span-full">
          {isOption && toNumber(part.sell_price) !== null ? (
            <p className="text-xs text-muted-foreground">
              {formatMoney(part.sell_price)} if picked
            </p>
          ) : null}
          {part.is_upgrade && toNumber(part.topup_amount) !== null ? (
            <p className="text-xs text-muted-foreground">+{formatMoney(part.topup_amount)}</p>
          ) : null}
        </div>
      )}
    </div>
  );
}

/**
 * The combo's own cover picture (AC-S5-2/S5-3/S5-5): Upload when there is
 * none, else the thumbnail with Replace and Clear. Through
 * `useProductComboImage`, the same query-cache mutation shape every other
 * combo edit on this page already uses - the list refetches itself on
 * success, so this control carries no `onChanged` callback of its own.
 */
function ComboImageControl({
  combo,
  canEdit,
}: {
  combo: ProductComboRow;
  canEdit: boolean;
}) {
  const { uploadMutateAsync, deleteMutateAsync, isUploading, isDeleting } =
    useProductComboImage(combo.host_product_id);
  const busy = isUploading || isDeleting;
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const handleFile = useCallback(
    async (file: File | undefined) => {
      if (!file) return;
      setError(null);
      try {
        await uploadMutateAsync({ comboId: combo.id, file });
      } catch (caught) {
        setError((caught as Error).message || 'Failed to upload the image');
      } finally {
        if (inputRef.current) inputRef.current.value = '';
      }
    },
    [combo.id, uploadMutateAsync],
  );

  const handleClear = useCallback(async () => {
    setError(null);
    try {
      await deleteMutateAsync(combo.id);
    } catch (caught) {
      setError((caught as Error).message || 'Failed to clear the image');
    }
  }, [combo.id, deleteMutateAsync]);

  if (!canEdit && !combo.image) return null;

  return (
    // `flex-wrap` (AC-S5-5 extended): the thumbnail, Replace/Clear and the
    // error text below crowd a single row off the edge at phone width.
    <div className="flex flex-wrap items-center gap-3 border-b p-3">
      {/* Images only (AC-S5-2) - the accept attribute plus the backend's own
          content-type check, which is what actually refuses a non-image. */}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        aria-label={`${combo.name} cover picture`}
        className="hidden"
        onChange={(event) => void handleFile(event.target.files?.[0])}
      />
      {combo.image ? (
        <>
          {/* A signed CDN URL, not a local/static asset next/image can
              optimise. */}
          <button
            type="button"
            aria-label={`Preview photo of ${combo.name}`}
            className="shrink-0 rounded-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setPreviewOpen(true)}
          >
            <img
              src={combo.image.url}
              alt=""
              className="size-14 rounded-md border object-cover"
            />
          </button>
          <AttachmentPreviewModal
            open={previewOpen}
            onOpenChange={setPreviewOpen}
            items={[
              {
                id: combo.image.attachment_id,
                name: combo.image.file_name ?? combo.name,
                url: combo.image.url,
              },
            ]}
          />
          {canEdit ? (
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => inputRef.current?.click()}
                disabled={busy}
              >
                {busy ? <LoaderCircleIcon className="size-4 animate-spin" /> : <Upload className="size-4" />}
                Replace
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void handleClear()}
                disabled={busy}
              >
                <X className="size-4" />
                Clear
              </Button>
            </div>
          ) : null}
        </>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
        >
          {busy ? (
            <LoaderCircleIcon className="size-4 animate-spin" />
          ) : (
            <ImagePlus className="size-4" />
          )}
          Upload picture
        </Button>
      )}
      {/* Its own line (AC-S5-5 extended): `w-full` forces a wrap onto a row
          by itself rather than squeezing in beside the buttons. */}
      {error ? <p className="w-full text-sm text-destructive">{error}</p> : null}
    </div>
  );
}

interface ComboBlockProps {
  combo: ProductComboRow;
  canEdit: boolean;
  isDeleting: boolean;
  removingPartId: string | null;
  onDelete: () => void;
  onRemovePart: (part: ProductComboPartRow) => void;
  onChoiceGroup: (part: ProductComboPartRow, label: string | null) => void;
  onPartWrite: (
    part: ProductComboPartRow,
    write: ProductComboPartUpdate,
    revert?: () => void,
  ) => void;
  onComboWrite: (write: ProductComboUpdate, revert?: () => void) => void;
  onRename: (name: string) => Promise<unknown>;
  onAddPart: (comboId: string, productId: string) => void;
  addPartError: string | null;
  isAddingPart: boolean;
}

function ComboBlock({
  combo,
  canEdit,
  isDeleting,
  removingPartId,
  onDelete,
  onRemovePart,
  onChoiceGroup,
  onPartWrite,
  onComboWrite,
  onRename,
  onAddPart,
  addPartError,
  isAddingPart,
}: ComboBlockProps) {
  const groupOptions = useMemo(
    () =>
      [
        ...new Set(
          combo.parts
            .map((part) => part.choice_group)
            .filter((label): label is string => !!label),
        ),
      ].map((label) => ({ value: label, label })),
    [combo.parts],
  );

  // Fixed parts first, then one block per choice group in the order the groups
  // first appear - so the package reads top to bottom the way the catalogue page
  // lists it, rather than alphabetically.
  // Upgrades are their own block after the groups, whatever group they were typed with.
  const upgradeParts = combo.parts.filter((part) => part.is_upgrade);
  const choiceParts = combo.parts.filter((part) => !part.is_upgrade);
  const fixedParts = choiceParts.filter((part) => !part.choice_group);
  const groups: { label: string; parts: ProductComboPartRow[] }[] = [];
  for (const part of choiceParts) {
    if (!part.choice_group) continue;
    const existing = groups.find((group) => group.label === part.choice_group);
    if (existing) existing.parts.push(part);
    else groups.push({ label: part.choice_group, parts: [part] });
  }

  const partRow = (part: ProductComboPartRow) => (
    <PartRow
      key={part.id}
      part={part}
      groupOptions={groupOptions}
      canEdit={canEdit}
      isRemoving={removingPartId === part.id}
      onChoiceGroup={(label) => onChoiceGroup(part, label)}
      onWrite={(write, revert) => onPartWrite(part, write, revert)}
      onRemove={() => onRemovePart(part)}
    />
  );

  return (
    <div className="rounded-lg border" data-combo-id={combo.id} data-testid="combo-block">
      <div className="flex flex-col gap-2 border-b p-3 sm:flex-row sm:items-center sm:justify-between">
        <ComboNameField name={combo.name} canEdit={canEdit} onRename={onRename} />
        {canEdit ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="shrink-0 justify-self-start"
            onClick={onDelete}
            disabled={isDeleting}
            aria-label={`Delete combo ${combo.name}`}
          >
            {isDeleting ? (
              <LoaderCircleIcon className="size-4 animate-spin" />
            ) : (
              <Trash2 className="size-4 text-destructive" />
            )}
          </Button>
        ) : null}
      </div>
      <ComboImageControl combo={combo} canEdit={canEdit} />
      {/* PRICETAG-LPSP: the combo's own price tag templates (manage permission only). */}
      <ComboTemplatesField comboId={combo.id} parts={combo.parts} />
      {/* The combo's own text and prices, printed on the tag (PRICETAG-COMBO).
          Same fields read-only and editing; edits save on blur. */}
      {canEdit ? (
        <div className="grid gap-3 border-b p-3 sm:grid-cols-2">
          <MoneyField
            id={`${combo.id}-list-price`}
            label="List price (RM)"
            value={combo.list_price}
            onSave={(next, revert) => onComboWrite({ list_price: next }, revert)}
            className="space-y-1.5"
          />
          <MoneyField
            id={`${combo.id}-sell-price`}
            label="Sell price (RM)"
            value={combo.sell_price}
            onSave={(next, revert) => onComboWrite({ sell_price: next }, revert)}
            className="space-y-1.5"
          />
          <div className="sm:col-span-2">
            <DescriptionField
              combo={combo}
              onSave={(next, revert) => onComboWrite({ description: next }, revert)}
            />
          </div>
          <div className="min-w-0 sm:col-span-2">
            <AccessoryListField kind="combo" ownerId={combo.id} ownerHostId={combo.host_product_id} label="Accessories included" canEdit />
          </div>
        </div>
      ) : (
        <div className="grid gap-3 border-b p-3 sm:grid-cols-2">
          <ReadOnlyField label="List price (RM)" value={toNumber(combo.list_price) === null ? null : formatMoney(combo.list_price)} />
          <ReadOnlyField label="Sell price (RM)" value={toNumber(combo.sell_price) === null ? null : formatMoney(combo.sell_price)} />
          <div className="min-w-0 space-y-0.5 sm:col-span-2">
            <p className="text-xs text-muted-foreground">Description</p>
            <RichTextView value={combo.description} />
          </div>
          <div className="min-w-0 sm:col-span-2">
            <AccessoryListField kind="combo" ownerId={combo.id} ownerHostId={combo.host_product_id} label="Accessories included" canEdit={false} />
          </div>
        </div>
      )}
      <div className="space-y-3 p-3">
        {combo.parts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No parts yet.</p>
        ) : null}
        {/* Its own scrollport (AC-S1-9): a kitchen-sink combo runs to a dozen
            parts and the page must not have to grow by a screen to hold one
            card. The Add part picker below stays put outside it. */}
        <div className="max-h-[22rem] space-y-3 overflow-y-auto">
          {fixedParts.length > 0 ? (
            <div className="space-y-3">{fixedParts.map(partRow)}</div>
          ) : null}
          {groups.map((group) => (
            <div key={group.label} className="space-y-3 rounded-md border border-dashed p-3">
              <p className="text-xs text-muted-foreground">
                {group.label}
                {group.parts.length > 1 ? ' - pick one' : ''}
              </p>
              {group.parts.map(partRow)}
            </div>
          ))}
          {upgradeParts.length > 0 ? (
            <div className="space-y-3 rounded-md border border-dashed p-3">
              <p className="text-xs text-muted-foreground">Upgrade</p>
              {upgradeParts.map(partRow)}
            </div>
          ) : null}
        </div>
        {canEdit ? (
          <div className="space-y-1.5">
            {/* The shared product search, server-searched and paged (AC-S1-3). It
                holds no value of its own - picking a product adds a part row and the
                picker returns to its placeholder - so there is nothing for a clear
                affordance to clear. */}
            <SearchableSelect
              value=""
              onChange={(productId) => {
                if (productId) onAddPart(combo.id, productId);
              }}
              fetchOptions={fetchProductOptions}
              paginated
              pageSize={PRODUCT_PAGE_SIZE}
              placeholder="Add part"
              emptyMessage="No products found."
              disabled={isAddingPart}
            />
            {addPartError ? <p className="text-sm text-destructive">{addPartError}</p> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * "Combos" (AC-S1-1 to AC-S1-5): the catalogue packages this product is sold as.
 * A cabinet printed on two catalogue pages carries two combos, each named the way
 * the catalogue names it; a part with no choice group always comes with the
 * package, and parts sharing a group are the options the customer picks one of.
 *
 * On the overview tab rather than Suppliers: a combo is what the product IS sold
 * as, not a fact about how it is bought (the Suppliers tab keeps the purchasing
 * bundling rules). A part reads the mirror of this on its own page, read-only, as
 * "Sold with" (`ProductSoldWithSection`).
 */
export function ProductCombosSection({ productId }: { productId: string }) {
  const [addOpen, setAddOpen] = useState(false);
  const [addPartError, setAddPartError] = useState<{ comboId: string; message: string } | null>(
    null,
  );
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canEdit = useHasPermission('master_data.products.edit');
  const { data: combos, isLoading, isError } = useProductCombos(productId);

  const partProductIds = useMemo(
    () => [...new Set((combos ?? []).flatMap((combo) => combo.parts.map((p) => p.product_id)))],
    [combos],
  );
  const comboDeletion = useProductComboDelete(productId, partProductIds);
  const partDeletion = useProductComboPartDelete(productId, partProductIds);
  const addPart = useAddProductComboPart(productId);
  const updatePart = useUpdateProductComboPart(productId);
  const updateCombo = useUpdateProductCombo(productId);

  const handleAddPart = useCallback(
    async (comboId: string, partProductId: string) => {
      setAddPartError(null);
      try {
        await addPart.mutateAsync({ comboId, write: { part_product_id: partProductId } });
      } catch (caught) {
        // Host-as-part and duplicate-part are answered under the picker, where
        // the choice that has to change was made (AC-S1-3).
        setAddPartError({
          comboId,
          message: (caught as Error).message || 'Failed to add the part',
        });
      }
    },
    [addPart],
  );

  // The new combo is created empty, so put it in view with its parts area ready
  // rather than leaving the reader to find it below the ones already there.
  const handleCreated = useCallback((comboId: string) => {
    requestAnimationFrame(() => {
      containerRef.current
        ?.querySelector(`[data-combo-id="${comboId}"]`)
        ?.scrollIntoView({ block: 'nearest' });
    });
  }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>Combos</CardTitle>
        {canEdit ? (
          <Button type="button" size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="size-4" />
            Add combo
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <SectionSkeleton rows={4} />
        ) : isError ? (
          <p className="text-sm text-destructive">
            Could not load combos. Try reloading the page.
          </p>
        ) : !combos || combos.length === 0 ? (
          // The sentence only: the header's own Add combo is the ONE call to
          // action, and a second button three lines under it reads as a second
          // thing to do.
          <p className="text-sm text-muted-foreground">No combos.</p>
        ) : (
          <div ref={containerRef} className="space-y-3">
            {combos.map((combo) => (
              <ComboBlock
                key={combo.id}
                combo={combo}
                canEdit={canEdit}
                isDeleting={comboDeletion.targetId === combo.id && comboDeletion.isPending}
                removingPartId={partDeletion.isPending ? partDeletion.targetId : null}
                onDelete={() => comboDeletion.run({ id: combo.id, subject: combo.name })}
                onRemovePart={(part) =>
                  partDeletion.run({ id: part.id, subject: `${part.code} from ${combo.name}` })
                }
                onChoiceGroup={(part, label) =>
                  updatePart.mutate({ partId: part.id, write: { choice_group: label } })
                }
                onPartWrite={(part, write, revert) =>
                  updatePart.mutate({ partId: part.id, write }, { onError: revert })
                }
                onComboWrite={(write, revert) =>
                  updateCombo.mutate({ comboId: combo.id, write }, { onError: revert })
                }
                onRename={(name) =>
                  updateCombo.mutateAsync({ comboId: combo.id, write: { name } })
                }
                onAddPart={handleAddPart}
                addPartError={
                  addPartError?.comboId === combo.id ? addPartError.message : null
                }
                isAddingPart={addPart.isPending}
              />
            ))}
          </div>
        )}
      </CardContent>
      {canEdit ? (
        <AddComboModal
          open={addOpen}
          onOpenChange={setAddOpen}
          productId={productId}
          onCreated={handleCreated}
        />
      ) : null}
    </Card>
  );
}

export default ProductCombosSection;

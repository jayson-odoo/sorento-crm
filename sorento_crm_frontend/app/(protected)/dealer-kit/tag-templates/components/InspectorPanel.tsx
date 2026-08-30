'use client';

/**
 * Right sidebar property inspector for the selected layer.
 *
 * Common props: position (x/y mm), size (w/h mm), rotation, locked, visible.
 * Type-specific sections render below based on `layer.props.kind`.
 */

import { useCallback } from 'react';
import { Braces, Eye, LayoutTemplate, Link2, Link2Off, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type {
  ImageFit,
  ImageMaskShape,
  PriceBadgeVariant,
  PriceDisplayType,
  ShapeType,
  SlotBinding,
  TagLayer,
  TagLayerProps,
} from '@/lib/dealer-kit/tag-template-types';
import { imageSourceOf } from '@/lib/dealer-kit/tag-template-types';
import { isDynamic } from '@/lib/dealer-kit/product-block';
import { ColorPicker } from './ColorPicker';

// ---------------------------------------------------------------------------
// Slot binding options
// ---------------------------------------------------------------------------

const SLOT_BINDING_OPTIONS = [
  { value: '__none__', label: '(None)' },
  { value: 'product_image', label: 'Product Image' },
  { value: 'code', label: 'Code' },
  { value: 'name', label: 'Name' },
  { value: 'dimensions', label: 'Dimensions' },
  { value: 'spec_lines', label: 'Spec Lines' },
  { value: 'included_accessories', label: 'Accessories' },
  { value: 'list_price', label: 'List Price' },
  { value: 'sell_price', label: 'Sell Price' },
  { value: 'badges', label: 'Badges' },
  { value: 'alternatives', label: 'Alternatives' },
  { value: 'set_members', label: 'Set Members' },
];

/**
 * The fonts every install has. Brand fonts uploaded as `Asset.kind='font'` are
 * appended to this list by the editor, so the inspector offers both without the
 * two lists having to know about each other.
 *
 * `Bebas Neue` and `Jost` are the seeded templates' stand-ins for the flyer's
 * licensed Century Gothic and Myriad Pro (D32). They are here because a select
 * that cannot display its own current value reads as a bug: without them the
 * font box on every seeded text layer would show blank, and picking anything
 * would silently restyle the tag. They are loaded by `TAG_FONT_STYLESHEET`.
 */
export const STATIC_FONT_OPTIONS: SearchableSelectOption[] = [
  { value: 'DM Sans', label: 'DM Sans' },
  { value: 'Inter', label: 'Inter' },
  { value: 'Bebas Neue', label: 'Bebas Neue' },
  { value: 'Jost', label: 'Jost' },
  { value: 'Arial', label: 'Arial' },
  { value: 'Georgia', label: 'Georgia' },
  { value: 'Times New Roman', label: 'Times New Roman' },
];

const FONT_WEIGHT_OPTIONS = [
  { value: '400', label: '400 Regular' },
  { value: '500', label: '500 Medium' },
  { value: '600', label: '600 Semi-bold' },
  { value: '700', label: '700 Bold' },
  { value: '800', label: '800 Extra-bold' },
  { value: '900', label: '900 Black' },
];

const SHAPE_TYPE_OPTIONS = [
  { value: 'rect', label: 'Rectangle' },
  { value: 'rounded_rect', label: 'Rounded Rect' },
  { value: 'ellipse', label: 'Ellipse' },
  { value: 'line', label: 'Line' },
];

const FIELD_KEY_OPTIONS = [
  { value: 'product_image', label: 'Product Image' },
  { value: 'code', label: 'Code' },
  { value: 'name', label: 'Name' },
  { value: 'dimensions', label: 'Dimensions' },
  { value: 'spec_lines', label: 'Spec Lines' },
];

const IMAGE_FIT_OPTIONS = [
  { value: 'cover', label: 'Cover' },
  { value: 'contain', label: 'Contain' },
];

const MASK_SHAPE_OPTIONS = [
  { value: 'none', label: 'None' },
  { value: 'circle', label: 'Circle' },
];

const PRICE_BADGE_VARIANT_OPTIONS = [
  { value: 'list_only', label: 'List price only' },
  { value: 'promo', label: 'Promotion (LP struck + SP)' },
];

const PRICE_TYPE_OPTIONS = [
  { value: 'list', label: 'List Price' },
  { value: 'sell', label: 'Sell Price' },
  { value: 'both', label: 'Both (LP struck + SP)' },
];

// ---------------------------------------------------------------------------
// Number input helper
// ---------------------------------------------------------------------------

function NumberInput({
  label,
  value,
  onChange,
  step = 1,
  min,
  max,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Input
        type="number"
        className="h-7 px-2 text-xs"
        value={value}
        step={step}
        min={min}
        max={max}
        onChange={(e) => {
          const n = parseFloat(e.target.value);
          if (!isNaN(n)) onChange(n);
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface InspectorPanelProps {
  layer: TagLayer | null;
  onUpdate: (id: string, changes: Partial<TagLayer>) => void;
  onUpdateProps: (id: string, changes: Partial<TagLayerProps>) => void;
  /** What this layer's slot currently resolves to, for the unlink/relink pair. */
  resolvedText?: string | null;
  /** Human-readable name of what the selected group is bound to. No UUIDs. */
  bindingLabel?: string | null;
  /** Static Google fonts plus the company's uploaded brand fonts. */
  fontOptions?: SearchableSelectOption[];
  /** Open the picture picker for an image layer. */
  onChooseImage?: (layerId: string) => void;
  /** Open the asset picker for a badge layer. */
  onChooseBadge?: (layerId: string) => void;
  /** Add a brand font without leaving the canvas. */
  onUploadFont?: () => void;
  /** Open the merge-field catalogue for this text layer (D59). */
  onInsertField?: () => void;
  /** Point this group's block at a different product or set. */
  onRebind?: (groupId: string) => void;
  /** Clear every text override inside this group. */
  onRelinkGroup?: (groupId: string) => void;
  /** Re-clone this whole tag from another template (D51, the request designer). */
  onUseTemplate?: () => void;
  /** The previewable block the selection sits in, if any (D53). */
  previewBlockId?: string | null;
  /** What that block is previewing with, `CODE - name`, or null. */
  previewBlockLabel?: string | null;
  onPreviewBlock?: (groupId: string) => void;
  onClearBlockPreview?: (groupId: string) => void;
}

export function InspectorPanel({
  layer,
  onUpdate,
  onUpdateProps,
  resolvedText,
  bindingLabel,
  fontOptions,
  onUploadFont,
  onInsertField,
  onChooseImage,
  onChooseBadge,
  onRebind,
  onRelinkGroup,
  onUseTemplate,
  previewBlockId,
  previewBlockLabel,
  onPreviewBlock,
  onClearBlockPreview,
}: InspectorPanelProps) {
  const update = useCallback(
    (changes: Partial<TagLayer>) => {
      if (layer) onUpdate(layer.id, changes);
    },
    [layer, onUpdate],
  );

  const updateProps = useCallback(
    (changes: Partial<TagLayerProps>) => {
      if (layer) onUpdateProps(layer.id, changes);
    },
    [layer, onUpdateProps],
  );

  if (!layer) {
    return (
      <div className="flex h-full flex-col border-l">
        <div className="flex h-10 shrink-0 items-center border-b px-3">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Inspector
          </span>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <p className="text-xs text-muted-foreground">Select a layer</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col border-l">
      <div className="flex h-10 shrink-0 items-center border-b px-3">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Inspector
        </span>
      </div>
      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-4 p-3">
          {/* -- Position & size -- */}
          <section>
            <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Transform
            </h4>
            <div className="grid grid-cols-2 gap-2">
              <NumberInput
                label="X (mm)"
                value={Math.round(layer.x_mm * 100) / 100}
                onChange={(v) => update({ x_mm: v })}
                step={0.5}
              />
              <NumberInput
                label="Y (mm)"
                value={Math.round(layer.y_mm * 100) / 100}
                onChange={(v) => update({ y_mm: v })}
                step={0.5}
              />
              <NumberInput
                label="W (mm)"
                value={Math.round(layer.width_mm * 100) / 100}
                onChange={(v) => update({ width_mm: v })}
                step={0.5}
                min={1}
              />
              <NumberInput
                label="H (mm)"
                value={Math.round(layer.height_mm * 100) / 100}
                onChange={(v) => update({ height_mm: v })}
                step={0.5}
                min={1}
              />
              <NumberInput
                label="Rotation"
                value={layer.rotation_deg}
                onChange={(v) => update({ rotation_deg: v })}
                step={1}
              />
              <NumberInput
                label="Z-Index"
                value={layer.z_index}
                onChange={(v) => update({ z_index: v })}
                step={1}
                min={0}
              />
            </div>
          </section>

          {/* -- Flags -- */}
          <section className="flex gap-4">
            <label className="flex items-center gap-1.5 text-xs">
              <Checkbox
                checked={layer.locked}
                onCheckedChange={(v) => update({ locked: !!v })}
              />
              Locked
            </label>
            <label className="flex items-center gap-1.5 text-xs">
              <Checkbox
                checked={layer.visible}
                onCheckedChange={(v) => update({ visible: !!v })}
              />
              Visible
            </label>
          </section>

          {/* -- Slot binding -- */}
          <section>
            <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Slot Binding
            </h4>
            <SearchableSelect
              value={layer.slot_binding ?? '__none__'}
              onChange={(v: string) =>
                update({ slot_binding: (v === '__none__' ? null : v) as SlotBinding })
              }
              options={SLOT_BINDING_OPTIONS}
            />
          </section>

          {/* -- Binding (a bound block, re-bound or relinked in one action) -- */}
          {layer.props.kind === 'group' && (
            <GroupBindingInspector
              layer={layer}
              bindingLabel={bindingLabel ?? null}
              onRebind={onRebind}
              onRelinkGroup={onRelinkGroup}
              onUseTemplate={onUseTemplate}
            />
          )}

          {/* -- Preview (D53): this block alone, against a real product -- */}
          {previewBlockId && onPreviewBlock && (
            <PreviewBlockInspector
              groupId={previewBlockId}
              label={previewBlockLabel ?? null}
              onPreview={onPreviewBlock}
              onClear={onClearBlockPreview}
            />
          )}

          {/* -- Type-specific props -- */}
          {layer.props.kind === 'text' && (
            <TextInspector
              layer={layer}
              props={layer.props}
              onChange={updateProps}
              onUpdate={update}
              resolvedText={resolvedText ?? null}
              fontOptions={fontOptions ?? STATIC_FONT_OPTIONS}
              onUploadFont={onUploadFont}
              onInsertField={onInsertField}
            />
          )}
          {layer.props.kind === 'price_badge' && (
            <PriceBadgeInspector props={layer.props} onChange={updateProps} />
          )}
          {layer.props.kind === 'shape' && (
            <ShapeInspector props={layer.props} onChange={updateProps} />
          )}
          {layer.props.kind === 'image' && (
            <ImageInspector
              layerId={layer.id}
              props={layer.props}
              onChange={updateProps}
              onChooseImage={onChooseImage}
            />
          )}
          {layer.props.kind === 'price_field' && (
            <PriceFieldInspector props={layer.props} onChange={updateProps} />
          )}
          {layer.props.kind === 'product_slot' && (
            <ProductSlotInspector props={layer.props} onChange={updateProps} />
          )}
          {layer.props.kind === 'badge' && (
            <BadgeInspector
              layerId={layer.id}
              props={layer.props}
              onChooseBadge={onChooseBadge}
            />
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Text inspector
// ---------------------------------------------------------------------------

function TextInspector({
  layer,
  props,
  onChange,
  onUpdate,
  resolvedText,
  fontOptions,
  onUploadFont,
  onInsertField,
}: {
  layer: TagLayer;
  props: Extract<TagLayerProps, { kind: 'text' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
  onUpdate: (changes: Partial<TagLayer>) => void;
  resolvedText: string | null;
  fontOptions: SearchableSelectOption[];
  onUploadFont?: () => void;
  onInsertField?: () => void;
}) {
  // A slot-bound layer is edited through `text_override`, never through
  // `props.text`: the binding survives the edit, so "Relink" is simply clearing
  // the override again rather than remembering what the product used to say.
  const bound = Boolean(layer.slot_binding);
  const overridden = bound && layer.text_override != null;
  // A typed-over layer holding a merge field is still following the product,
  // so it says so rather than showing the amber broken-link note (D57).
  const dynamic = isDynamic(layer);
  const shown = bound
    ? layer.text_override ?? resolvedText ?? props.text
    : props.text;

  const handleContent = (value: string) => {
    if (bound) onUpdate({ text_override: value });
    else onChange({ ...props, text: value });
  };

  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Text
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">Content</Label>
            <div className="flex items-center gap-1">
              {overridden && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 text-[10px]"
                  onClick={() => onUpdate({ text_override: null })}
                >
                  <Link2 className="mr-1 size-3" />
                  Relink
                </Button>
              )}
              {onInsertField && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 text-[10px]"
                  onClick={onInsertField}
                >
                  <Braces className="mr-1 size-3" />
                  Insert field
                </Button>
              )}
            </div>
          </div>
          <textarea
            className="min-h-[60px] w-full rounded-md border bg-background px-2 py-1 text-xs"
            value={shown}
            onChange={(e) => handleContent(e.target.value)}
          />
          {overridden && !dynamic && (
            <span className="flex items-center gap-1 text-[10px] text-amber-600">
              <Link2Off className="size-3" />
              Unlinked from product data
            </span>
          )}
          {dynamic && (
            <span className="flex items-center gap-1 text-[10px] text-sky-600">
              <Braces className="size-3" />
              Draws from product data
            </span>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">Font Family</Label>
            {onUploadFont && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 px-1.5 text-[10px]"
                onClick={onUploadFont}
              >
                Upload font
              </Button>
            )}
          </div>
          <SearchableSelect
            value={props.fontFamily}
            onChange={(v: string) => onChange({ ...props, fontFamily: v })}
            options={fontOptions}
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <NumberInput
            label="Font Size"
            value={props.fontSize}
            onChange={(v) => onChange({ ...props, fontSize: v })}
            step={0.5}
            min={4}
          />
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Font Weight</Label>
            <SearchableSelect
              value={String(props.fontWeight)}
              onChange={(v: string) => onChange({ ...props, fontWeight: parseInt(v, 10) })}
              options={FONT_WEIGHT_OPTIONS}
            />
          </div>
        </div>
        <ColorPicker
          label="Colour"
          value={props.color}
          onChange={(v) => onChange({ ...props, color: v })}
        />
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Align</Label>
          <div className="flex gap-1">
            {(['left', 'center', 'right'] as const).map((a) => (
              <button
                key={a}
                type="button"
                className={`flex-1 rounded border px-2 py-0.5 text-xs ${
                  props.align === a
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-input hover:bg-accent'
                }`}
                onClick={() => onChange({ ...props, align: a })}
              >
                {a.charAt(0).toUpperCase() + a.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <NumberInput
            label="Line Height"
            value={props.lineHeight}
            onChange={(v) => onChange({ ...props, lineHeight: v })}
            step={0.1}
            min={0.5}
          />
          <NumberInput
            label="Letter Spacing"
            value={props.letterSpacing}
            onChange={(v) => onChange({ ...props, letterSpacing: v })}
            step={0.1}
          />
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Shape inspector
// ---------------------------------------------------------------------------

function ShapeInspector({
  props,
  onChange,
}: {
  props: Extract<TagLayerProps, { kind: 'shape' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
}) {
  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Shape
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Shape Type</Label>
          <SearchableSelect
            value={props.shape}
            onChange={(v: string) => onChange({ ...props, shape: v as ShapeType })}
            options={SHAPE_TYPE_OPTIONS}
          />
        </div>
        <ColorPicker
          label="Fill"
          value={props.fill}
          onChange={(v) => onChange({ ...props, fill: v })}
        />
        <ColorPicker
          label="Stroke"
          value={props.stroke}
          onChange={(v) => onChange({ ...props, stroke: v })}
        />
        <div className="grid grid-cols-2 gap-2">
          <NumberInput
            label="Stroke Width"
            value={props.strokeWidth}
            onChange={(v) => onChange({ ...props, strokeWidth: v })}
            step={0.25}
            min={0}
          />
          <NumberInput
            label="Corner Radius"
            value={props.cornerRadius}
            onChange={(v) => onChange({ ...props, cornerRadius: v })}
            step={0.5}
            min={0}
          />
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Image inspector
// ---------------------------------------------------------------------------

function ImageInspector({
  layerId,
  props,
  onChange,
  onChooseImage,
}: {
  layerId: string;
  props: Extract<TagLayerProps, { kind: 'image' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
  onChooseImage?: (layerId: string) => void;
}) {
  const source = imageSourceOf(props);
  // Never the id itself: a UUID has no business on a screen.
  const sourceLabel =
    source == null
      ? 'None chosen'
      : source.type === 'product_attachment'
        ? 'Product photo'
        : 'Asset library';

  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Image
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-muted-foreground">{sourceLabel}</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => onChooseImage?.(layerId)}
            disabled={!onChooseImage}
          >
            Choose image
          </Button>
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Fit</Label>
          <SearchableSelect
            value={props.fit}
            onChange={(v: string) => onChange({ ...props, fit: v as ImageFit })}
            options={IMAGE_FIT_OPTIONS}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Mask</Label>
          <SearchableSelect
            value={props.maskShape ?? 'none'}
            onChange={(v: string) =>
              onChange({ ...props, maskShape: v as ImageMaskShape })
            }
            options={MASK_SHAPE_OPTIONS}
          />
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Price badge inspector (D26)
// ---------------------------------------------------------------------------

function PriceBadgeInspector({
  props,
  onChange,
}: {
  props: Extract<TagLayerProps, { kind: 'price_badge' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
}) {
  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Price Badge
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Variant</Label>
          <SearchableSelect
            value={props.variant}
            onChange={(v: string) =>
              onChange({ ...props, variant: v as PriceBadgeVariant })
            }
            options={PRICE_BADGE_VARIANT_OPTIONS}
          />
        </div>
        <ColorPicker
          label="Box Fill"
          value={props.fill}
          onChange={(v) => onChange({ ...props, fill: v })}
        />
        <ColorPicker
          label="Text Colour"
          value={props.textColor}
          onChange={(v) => onChange({ ...props, textColor: v })}
        />
        <NumberInput
          label="Corner Radius"
          value={props.cornerRadius}
          onChange={(v) => onChange({ ...props, cornerRadius: v })}
          step={0.5}
          min={0}
        />
        <label className="flex items-center gap-1.5 text-xs">
          <Checkbox
            checked={props.showNett}
            onCheckedChange={(v) => onChange({ ...props, showNett: !!v })}
          />
          Show NETT
        </label>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Preview inspector (D53)
// ---------------------------------------------------------------------------

/**
 * Preview THIS block, from wherever the selection is inside it.
 *
 * The toolbar asks about the whole tag; a designer working on one alternative
 * wants that alternative, and going back to the toolbar to pick it out of a
 * list of four is a longer way round than the block already selected.
 */
function PreviewBlockInspector({
  groupId,
  label,
  onPreview,
  onClear,
}: {
  groupId: string;
  label: string | null;
  onPreview: (groupId: string) => void;
  onClear?: (groupId: string) => void;
}) {
  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Preview
      </h4>
      {label ? (
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="min-w-0 flex-1 truncate text-left text-[11px] font-medium hover:underline"
            onClick={() => onPreview(groupId)}
            title={label}
          >
            {label}
          </button>
          <button
            type="button"
            className="shrink-0 rounded-sm p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={() => onClear?.(groupId)}
            title="Stop previewing this block"
          >
            <X className="size-3" />
          </button>
        </div>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 w-full text-xs"
          onClick={() => onPreview(groupId)}
        >
          <Eye className="mr-1 size-3" />
          Preview this block with...
        </Button>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Group binding inspector
// ---------------------------------------------------------------------------

function GroupBindingInspector({
  layer,
  bindingLabel,
  onRebind,
  onRelinkGroup,
  onUseTemplate,
}: {
  layer: TagLayer;
  bindingLabel: string | null;
  onRebind?: (groupId: string) => void;
  onRelinkGroup?: (groupId: string) => void;
  onUseTemplate?: () => void;
}) {
  const props = layer.props as Extract<TagLayerProps, { kind: 'group' }>;
  const binding = props.binding;
  const isSet = Boolean(binding?.product_set_id);

  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Bound To
      </h4>
      {binding ? (
        <div className="flex flex-col gap-2">
          <p className="text-[11px] font-medium">
            {bindingLabel ?? (isSet ? 'Product set' : 'Product')}
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 flex-1 text-xs"
              onClick={() => onRebind?.(layer.id)}
              disabled={!onRebind}
            >
              Change {isSet ? 'set' : 'product'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => onRelinkGroup?.(layer.id)}
              disabled={!onRelinkGroup}
            >
              <Link2 className="mr-1 size-3" />
              Relink all
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-[10px] text-muted-foreground">
          This group is not bound to a product or set.
        </p>
      )}
      {onUseTemplate && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="mt-2 h-7 w-full text-xs"
          onClick={onUseTemplate}
        >
          <LayoutTemplate className="mr-1 size-3" />
          Use template...
        </Button>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Price field inspector
// ---------------------------------------------------------------------------

function PriceFieldInspector({
  props,
  onChange,
}: {
  props: Extract<TagLayerProps, { kind: 'price_field' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
}) {
  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Price Field
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Price Type</Label>
          <SearchableSelect
            value={props.priceType}
            onChange={(v: string) =>
              onChange({ ...props, priceType: v as PriceDisplayType })
            }
            options={PRICE_TYPE_OPTIONS}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Format</Label>
          <Input
            className="h-7 px-2 text-xs"
            value={props.format}
            onChange={(e) => onChange({ ...props, format: e.target.value })}
          />
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Product slot inspector
// ---------------------------------------------------------------------------

function ProductSlotInspector({
  props,
  onChange,
}: {
  props: Extract<TagLayerProps, { kind: 'product_slot' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
}) {
  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Product Slot
      </h4>
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Field Key</Label>
        <SearchableSelect
          value={props.fieldKey}
          onChange={(v: string) => onChange({ ...props, fieldKey: v })}
          options={FIELD_KEY_OPTIONS}
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Badge inspector
// ---------------------------------------------------------------------------

function BadgeInspector({
  layerId,
  props,
  onChooseBadge,
}: {
  layerId: string;
  props: Extract<TagLayerProps, { kind: 'badge' }>;
  onChooseBadge?: (layerId: string) => void;
}) {
  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Badge
      </h4>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-muted-foreground">
          {props.assetId ? 'Chosen' : 'None chosen'}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => onChooseBadge?.(layerId)}
          disabled={!onChooseBadge}
        >
          Choose badge
        </Button>
      </div>
    </section>
  );
}

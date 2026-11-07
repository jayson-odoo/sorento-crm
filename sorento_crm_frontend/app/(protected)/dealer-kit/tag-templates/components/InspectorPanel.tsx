'use client';

/**
 * Right sidebar property inspector for the selected layer.
 *
 * Common props: position (x/y mm), size (w/h mm), rotation, locked, visible.
 * Type-specific sections render below based on `layer.props.kind`.
 */

import { useCallback, useId, useMemo } from 'react';
import type { AccessoriesLayerProps, FeatureIconsLayerProps } from '@/lib/dealer-kit/tag-template-types';
import { featureIconFit } from '@/lib/dealer-kit/feature-icons';
import {
  accessoryBoxLayout,
  accessoryHeaderStyle,
  accessoryLineStyle,
  itemLayoutOf,
  type AccessoryLineStyle,
} from '@/lib/dealer-kit/accessory-box';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Bold,
  Braces,
  Copy,
  Eye,
  FlipHorizontal2,
  FlipVertical2,
  Italic,
  LayoutTemplate,
  Link2,
  Link2Off,
  Strikethrough,
  Underline,
  X,
} from 'lucide-react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { LiveNumberInput } from '@/components/ui/number-input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type {
  ImageFit,
  ImageMaskShape,
  LayerPadding,
  PriceBadgeVariant,
  ShapeType,
  SlotBinding,
  TagLayer,
  LayerShowWhen,
  TagLayerProps,
  TagPartData,
  TagSlots,
  SubjectSlot,
} from '@/lib/dealer-kit/tag-template-types';
import { imageSourceOf } from '@/lib/dealer-kit/tag-template-types';
import { isCropped } from '@/lib/dealer-kit/image-crop';
import { defaultPolygonPoints } from '@/lib/dealer-kit/polygon-path';
import { priceBadgeInsets, priceBadgeTypography } from '@/lib/dealer-kit/price-badge';
import { isDynamic, slotLabel } from '@/lib/dealer-kit/product-block';
import { comboPositions } from '@/lib/dealer-kit/combo-slots';
import { hasSubjectAwareToken, type SpecKeyOption } from '@/lib/dealer-kit/merge-fields';
import { tagColours } from '@/lib/dealer-kit/colour';
import { ColorPicker } from '@/components/common/ColorPicker';
import { richPlainText, toEditorHtml } from '@/lib/dealer-kit/rich-text';
import { contentFromEditorHtml } from '@/lib/dealer-kit/layer-content';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import type { Editor } from '@tiptap/react';

// ---------------------------------------------------------------------------
// Slot binding options
// ---------------------------------------------------------------------------

const SLOT_BINDING_OPTIONS: SearchableSelectOption[] = [
  // The Combo group leads the list: the select renders groups in order of first
  // appearance, so listing it before the ungrouped options puts it above them.
  { value: 'combo_image', label: 'Combo Photo', group: 'Combo' },
  { value: 'combo_name', label: 'Combo Name', group: 'Combo' },
  { value: 'combo_description', label: 'Combo Description', group: 'Combo' },
  { value: 'combo_choices', label: 'Combo Choices', group: 'Combo' },
  { value: 'combo_topups', label: 'Combo Top-ups', group: 'Combo' },
  { value: '__none__', label: '(None)' },
  { value: 'product_image', label: 'Product Image' },
  // PS-SPEC-SHEET: the technical drawing (quotation line's frozen drawing on a spec sheet).
  { value: 'drawing', label: 'Drawing' },
  { value: 'code', label: 'Code' },
  { value: 'name', label: 'Name' },
  { value: 'dimensions', label: 'Dimensions' },
  { value: 'spec_lines', label: 'Spec Lines' },
  { value: 'included_accessories', label: 'Accessories' },
  { value: 'list_price', label: 'List Price' },
  { value: 'sell_price', label: 'Sell Price' },
  { value: 'price', label: 'Price (LP or SP)' },
  { value: 'price_label', label: 'Price label' },
  { value: 'badges', label: 'Badges' },
  { value: 'alternatives', label: 'Alternatives' },
  { value: 'set_members', label: 'Set Members' },
  { value: 'barcode', label: 'Barcode' },
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
  { value: 'polygon', label: 'Polygon' },
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
  { value: 'stretch', label: 'Stretch' },
];

const MASK_SHAPE_OPTIONS = [
  { value: 'none', label: 'None' },
  { value: 'circle', label: 'Circle' },
];

const PRICE_BADGE_VARIANT_OPTIONS = [
  { value: 'list_only', label: 'List price only' },
  { value: 'promo', label: 'Promotion (LP struck + SP)' },
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
  /** Null draws an EMPTY box: the layer has not named a value for this. */
  value: number | null;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id} className="text-xs text-muted-foreground">
        {label}
      </Label>
      <LiveNumberInput
        id={id}
        className="h-7 px-2 text-xs"
        value={value}
        step={step}
        min={min}
        max={max}
        rules={{ min, max }}
        onCommit={onChange}
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
  /** The whole tag, so the colour picker can derive "This tag" (S3, AC-S3-5). */
  layers?: TagLayer[];
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
  /** The Content box's editor, so Insert field lands at its caret (check `isDestroyed`). */
  onContentEditorReady?: (editor: Editor) => void;
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
  /** Whether this layer is currently in edit-points mode (S5). */
  editingPoints?: boolean;
  /** Toggle edit-points mode for this layer (S5); a polygon or a boxed
   * list-only price badge only. */
  onToggleEditPoints?: (layerId: string) => void;
  /**
   * D7 (AC-S4-1/S4-2): the combo tag's own parts, in package order - the
   * Product picker's option list. Absent or empty means a single-product
   * tag, so no picker shows on ANY layer.
   */
  subjectParts?: TagPartData[];
  /** The previewed combo's positions (template editor only); null/absent = nothing previewed. */
  subjectSlots?: TagSlots | null;
  /** The parent's own code, for the picker's first entry. */
  subjectParentCode?: string | null;
  /** PS-SPEC-SHEET: a spec sheet page template, so layers can carry "Show only when". */
  specSheet?: boolean;
  /** The spec registry keys, for the "Show only when spec is Yes" picker. */
  specKeys?: SpecKeyOption[];
  /** Feature icons: open the icon library (upload, rename); the rules live on the spec values. */
  onManageIcons?: () => void;
  /** Feature icons: how many icons the previewed product reads for the selected layer. */
  featureIconCount?: number;
  /** Accessories: how many entries the previewed tag lists for the selected layer, and how many
   *  text lines its cards take (`accessoryLineCount`). Absent with nothing previewed. */
  accessoryFit?: { count: number; lines: number };
}

export function InspectorPanel({
  layer,
  onUpdate,
  onUpdateProps,
  layers,
  resolvedText,
  bindingLabel,
  fontOptions,
  onUploadFont,
  onInsertField,
  onContentEditorReady,
  onChooseImage,
  onChooseBadge,
  onRebind,
  onRelinkGroup,
  onUseTemplate,
  previewBlockId,
  previewBlockLabel,
  onPreviewBlock,
  onClearBlockPreview,
  editingPoints,
  onToggleEditPoints,
  subjectParts,
  subjectSlots,
  subjectParentCode,
  specSheet = false,
  specKeys,
  onManageIcons,
  featureIconCount,
  accessoryFit,
}: InspectorPanelProps) {
  const usedColours = useMemo(() => tagColours(layers ?? []), [layers]);

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

  // D7/AC-S4-1/S4-2: the Product picker shows on any layer that reads
  // product data - a combo tag only (single-product tags have no parts to
  // point at, so `subjectParts` arrives empty and the section never renders).
  //
  // Browser finding: the designer's own photo slots are `image` layers
  // carrying `slot_binding: 'product_image'`, not `product_slot` - the
  // Product select never appeared on the image slot the walk selected. A
  // text layer can carry a slot_binding too (`code`, `name`, ...), same
  // gap. Keyed on "does this layer read product data" generally now:
  // the four kinds that always do, a text layer with a `{{product.*}}` /
  // `{{spec.*}}` token, OR ANY layer whose own `slot_binding` names a
  // product field.
  //
  // Review round 2: `slot_binding != null` on its own let a SHAPE, a plain
  // `badge` or a `group` offer the picker - none of those three carry
  // `subjectPart` in `tag-template-types.ts`, so the pick was written onto
  // props no resolver ever reads and the layer drew the parent regardless.
  // Both halves have to hold: a kind that can carry the subject, AND a
  // layer that actually reads product data.
  const carriesSubjectPart =
    layer.props.kind === 'product_slot' ||
    layer.props.kind === 'price_badge' ||
    layer.props.kind === 'barcode' ||
    layer.props.kind === 'text' ||
    layer.props.kind === 'image' ||
    layer.props.kind === 'feature_icons' ||
    layer.props.kind === 'accessories';
  const readsProductData =
    layer.props.kind === 'feature_icons' ||
    layer.props.kind === 'accessories' ||
    layer.props.kind === 'product_slot' ||
    layer.props.kind === 'price_badge' ||
    layer.props.kind === 'barcode' ||
    (layer.props.kind === 'text' &&
      hasSubjectAwareToken(layer.text_override ?? layer.props.text)) ||
    layer.slot_binding != null;
  const isSubjectAwareKind = carriesSubjectPart && readsProductData;
  // The template editor has no line, so no parts: it picks a POSITION in the combo instead.
  const showSubjectPicker =
    isSubjectAwareKind && (subjectParts ? subjectParts.length > 0 : !specSheet);

  // The same eligibility r4b's `cornerHandleLayer` already checks on the
  // canvas side (S5): a polygon shape, or a price badge whose box IS its
  // own shape (a plain rectangle badge has no corners of its own to edit).
  const canEditPoints =
    (layer.props.kind === 'shape' && layer.props.shape === 'polygon') ||
    (layer.props.kind === 'price_badge' &&
      layer.props.variant === 'list_only' &&
      layer.props.showBox === true);

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
            <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
              Transform
            </h4>
            <div className="grid grid-cols-2 gap-2">
              <NumberInput
                label="X (mm)"
                value={Math.round(layer.x_mm * 100) / 100}
                onChange={(v) => update({ x_mm: v })}
                step={0.25}
              />
              <NumberInput
                label="Y (mm)"
                value={Math.round(layer.y_mm * 100) / 100}
                onChange={(v) => update({ y_mm: v })}
                step={0.25}
              />
              <NumberInput
                label="W (mm)"
                value={Math.round(layer.width_mm * 100) / 100}
                onChange={(v) => update({ width_mm: v })}
                step={0.25}
                min={1}
              />
              <NumberInput
                label="H (mm)"
                value={Math.round(layer.height_mm * 100) / 100}
                onChange={(v) => update({ height_mm: v })}
                step={0.25}
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

          {/* -- Edit points (S5): a polygon, or a boxed list-only price
              badge - the same shape by another name - toggles between the
              Transformer's resize anchors (select mode) and its own vertex
              + edge handles (edit-points mode). Double-click the shape or
              Enter does the same thing; this is the discoverable path for
              anyone who never finds either. */}
          {canEditPoints && onToggleEditPoints && (
            <section>
              <Button
                type="button"
                variant={editingPoints ? 'primary' : 'secondary'}
                size="sm"
                className="w-full"
                // Same eligibility `cornerHandleLayer` gates the canvas
                // side on (AC-S5-5 review): a locked or hidden layer has
                // no corner handles to edit points OF, so the button
                // disables rather than staying clickable into a mode with
                // nothing for it to show.
                disabled={layer.locked || !layer.visible}
                onClick={() => onToggleEditPoints(layer.id)}
              >
                {editingPoints ? 'Done editing points' : 'Edit points'}
              </Button>
            </section>
          )}

          {/* -- Slot binding -- */}
          <section>
            <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
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

          {/* -- Subject (D7/AC-S4-1): which of a combo tag's products this
              layer reads. Parent first and default, so an existing design
              renders unchanged (AC-S4-4); a price badge's list also offers
              Tag total, the roll-up it always printed. */}
          {showSubjectPicker && (
            <SubjectInspector
              props={layer.props}
              parts={subjectParts}
              slots={subjectSlots}
              parentCode={subjectParentCode ?? ''}
              onChange={updateProps}
            />
          )}

          {/* -- PS-SPEC-SHEET: print this layer only when the page's data says so -- */}
          {specSheet && (
            <ShowWhenInspector
              layer={layer}
              specKeys={specKeys ?? []}
              onChange={(show_when) => update({ show_when })}
            />
          )}

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
              onContentEditorReady={onContentEditorReady}
              usedColours={usedColours}
            />
          )}
          {layer.props.kind === 'price_badge' && (
            <PriceBadgeInspector
              props={layer.props}
              onChange={updateProps}
              usedColours={usedColours}
              fontOptions={fontOptions ?? STATIC_FONT_OPTIONS}
              onUploadFont={onUploadFont}
            />
          )}
          {layer.props.kind === 'shape' && (
            <ShapeInspector props={layer.props} onChange={updateProps} usedColours={usedColours} />
          )}
          {layer.props.kind === 'image' && (
            <ImageInspector
              layerId={layer.id}
              props={layer.props}
              onChange={updateProps}
              onChooseImage={onChooseImage}
            />
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
          {layer.props.kind === 'feature_icons' && (
            <FeatureIconsInspector
              props={layer.props}
              onManageIcons={onManageIcons}
              iconCount={featureIconCount ?? 0}
              boxWidth_mm={layer.width_mm}
              onChange={(changes) => onUpdateProps(layer.id, { ...layer.props, ...changes })}
            />
          )}
          {layer.props.kind === 'accessories' && (
            <AccessoriesInspector
              props={layer.props}
              fit={accessoryFit}
              boxWidth_mm={layer.width_mm}
              boxHeight_mm={layer.height_mm}
              usedColours={usedColours}
              fontOptions={fontOptions ?? STATIC_FONT_OPTIONS}
              onUploadFont={onUploadFont}
              onChange={(changes) => onUpdateProps(layer.id, { ...layer.props, ...changes })}
            />
          )}
          {layer.props.kind === 'barcode' && (
            <BarcodeInspector
              layer={layer}
              props={layer.props}
              onChange={updateProps}
              onUpdate={update}
              resolvedText={resolvedText ?? null}
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

const PRICE_SLOTS: string[] = ['list_price', 'sell_price', 'price'];

function TextInspector({
  layer,
  props,
  onChange,
  onUpdate,
  resolvedText,
  fontOptions,
  onUploadFont,
  onInsertField,
  onContentEditorReady,
  usedColours,
}: {
  layer: TagLayer;
  props: Extract<TagLayerProps, { kind: 'text' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
  onUpdate: (changes: Partial<TagLayer>) => void;
  resolvedText: string | null;
  fontOptions: SearchableSelectOption[];
  onUploadFont?: () => void;
  onInsertField?: () => void;
  /** The Content box's editor, so Insert field lands at its caret (check `isDestroyed`). */
  onContentEditorReady?: (editor: Editor) => void;
  usedColours: string[];
}) {
  // A slot-bound layer is edited through `text_override`, never through
  // `props.text`: the binding survives the edit, so "Relink" is simply clearing
  // the override again rather than remembering what the product used to say.
  const bound = Boolean(layer.slot_binding);
  const overridden = bound && layer.text_override != null;
  // A typed-over layer holding a merge field is still following the product,
  // so it says so rather than showing the amber broken-link note (D57).
  const dynamic = isDynamic(layer);
  // R8: a layer bound to a description slot shows the description as plain text, read-only; it
  // is edited on the product / combo page, never as raw markup here.
  const descriptionBound =
    (layer.slot_binding === 'combo_description' || layer.slot_binding === 'price_tag_description') &&
    layer.text_override == null;
  const shown = descriptionBound
    ? richPlainText(resolvedText ?? props.text)
    : bound
      ? layer.text_override ?? resolvedText ?? props.text
      : props.text;

  const contentLabelId = useId();

  const handleContent = (value: string) => {
    // Nothing changed (the box re-reporting what it was given): writing it would turn a bound
    // layer's live value into a typed override (review B1).
    if (value === shown) return;
    if (bound) onUpdate({ text_override: value });
    else onChange({ ...props, text: value });
  };

  return (
    <section>
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Text
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <Label id={contentLabelId} className="text-xs text-muted-foreground">
              Content
            </Label>
            <div className="flex items-center gap-1">
              {overridden && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 text-2xs"
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
                  className="h-6 px-1.5 text-2xs"
                  onClick={onInsertField}
                >
                  <Braces className="mr-1 size-3" />
                  Insert field
                </Button>
              )}
            </div>
          </div>
          {descriptionBound ? (
            <textarea
              aria-labelledby={contentLabelId}
              className="min-h-[60px] w-full rounded-md border bg-background px-2 py-1 text-xs"
              value={shown}
              readOnly
            />
          ) : (
            // DESIGNER-RICH-TEXT: bold / italic / underline / strike / colour per selection; the
            // layer's font, size, weight and colour stay the default for unmarked text. Content
            // with no formatting is stored as plain text, as before (`contentFromEditorHtml`).
            <RichTextEditor
              key={layer.id}
              toolbar="inline"
              mergeFields
              minHeight={60}
              className="text-xs [&_.ProseMirror]:px-2 [&_.ProseMirror]:py-1 [&_.ProseMirror_p]:my-0"
              value={toEditorHtml(shown)}
              onChange={(html) => handleContent(contentFromEditorHtml(html))}
              onEditorReady={onContentEditorReady}
              aria-labelledby={contentLabelId}
            />
          )}
          {overridden && !dynamic && (
            <span className="flex items-center gap-1 text-2xs text-amber-600">
              <Link2Off className="size-3" />
              Unlinked from product data
            </span>
          )}
          {dynamic && (
            <span className="flex items-center gap-1 text-2xs text-sky-600">
              <Braces className="size-3" />
              Draws from product data
            </span>
          )}
          {/* D21 (AC-S16-1/S16-2): the inline canvas edit still shows the
              SOURCE (the token) - this read-only line is the only copy
              surface for what will actually print. */}
          {dynamic && resolvedText != null && (
            <div className="flex items-center justify-between gap-2 rounded-md border bg-muted/40 px-2 py-1">
              <span className="truncate text-xs" title={resolvedText}>
                {resolvedText}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 shrink-0 px-1.5 text-2xs"
                onClick={() => {
                  void navigator.clipboard.writeText(resolvedText);
                  toast.success('Copied');
                }}
              >
                <Copy className="mr-1 size-3" />
                Copy rendered text
              </Button>
            </div>
          )}
        </div>
        {PRICE_SLOTS.includes(layer.slot_binding as string) && (
          <label className="flex items-center gap-1.5 text-xs">
            <Checkbox
              checked={props.showCurrency ?? false}
              onCheckedChange={(v) => onChange({ ...props, showCurrency: !!v })}
            />
            Show currency
          </label>
        )}
        <TypographyControls
          values={{
            fontFamily: props.fontFamily,
            fontSize: props.fontSize,
            fontWeight: props.fontWeight,
            italic: props.italic ?? false,
            underline: props.underline ?? false,
            strikethrough: props.strikethrough ?? false,
            align: props.align,
            lineHeight: props.lineHeight,
            letterSpacing: props.letterSpacing,
            padding: props.padding ?? ZERO_PADDING,
          }}
          onChange={(changes) => onChange({ ...props, ...changes })}
          colour={props.color}
          onColourChange={(v) => onChange({ ...props, color: v })}
          usedColours={usedColours}
          fontOptions={fontOptions}
          onUploadFont={onUploadFont}
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Typography controls, shared by the text and price badge sections (S6b)
// ---------------------------------------------------------------------------

/** Every side at 0mm - an absent `padding` reads as this (S3). */
const ZERO_PADDING: LayerPadding = { top: 0, right: 0, bottom: 0, left: 0 };

/**
 * Top/Right/Bottom/Left, one `NumberInput` each (S3, S3b).
 *
 * Shared by the Padding row every layer that has one shows, and the Margin
 * row a price badge shows above it (S3b, AC-6) - the same four fields either
 * way, only which `LayerPadding` they read and write differs.
 */
function SidesInput({
  value,
  onChange,
}: {
  value: LayerPadding;
  onChange: (value: LayerPadding) => void;
}) {
  return (
    <div className="grid grid-cols-4 gap-2">
      <NumberInput
        label="Top"
        value={value.top}
        onChange={(v) => onChange({ ...value, top: v })}
        step={0.5}
        min={0}
      />
      <NumberInput
        label="Right"
        value={value.right}
        onChange={(v) => onChange({ ...value, right: v })}
        step={0.5}
        min={0}
      />
      <NumberInput
        label="Bottom"
        value={value.bottom}
        onChange={(v) => onChange({ ...value, bottom: v })}
        step={0.5}
        min={0}
      />
      <NumberInput
        label="Left"
        value={value.left}
        onChange={(v) => onChange({ ...value, left: v })}
        step={0.5}
        min={0}
      />
    </div>
  );
}

/** What the controls SHOW. Null = the layer has not named one. */
interface TypographyValues {
  fontFamily: string;
  fontSize: number | null;
  fontWeight: number;
  italic: boolean;
  underline: boolean;
  strikethrough: boolean;
  align: 'left' | 'center' | 'right';
  lineHeight: number | null;
  letterSpacing: number;
  /** Absent on the layer reads as `ZERO_PADDING` (S3) - never null here. */
  padding: LayerPadding;
}

/**
 * What a control WRITES. Never null: a box the user typed in has a number in
 * it, and nothing here can put a field back to "unnamed".
 */
type TypographyChanges = Partial<Omit<TypographyValues, 'fontSize' | 'lineHeight'>> & {
  fontSize?: number;
  lineHeight?: number;
};

/**
 * Font family, size, B/I/U/S, weight, colour, alignment and spacing.
 *
 * One component for the text layer and the price badge (S6b, AC-S6-4): the
 * badge's figure is text a designer wants to set like any other, and a second
 * copy of these nine controls is where the two would start behaving
 * differently. The colour field is passed in rather than read off a fixed
 * key, because a badge keeps its figure's colour in `textColor`.
 */
function TypographyControls({
  values,
  onChange,
  colour,
  colourLabel = 'Colour',
  onColourChange,
  usedColours,
  fontOptions,
  onUploadFont,
  margin,
  onMarginChange,
  singleLine = false,
}: {
  values: TypographyValues;
  onChange: (changes: TypographyChanges) => void;
  colour: string;
  colourLabel?: string;
  onColourChange: (value: string) => void;
  usedColours: string[];
  fontOptions: SearchableSelectOption[];
  onUploadFont?: () => void;
  /**
   * Present only for a price badge (S3b, AC-6): drawn as its own `Margin
   * (mm)` group ABOVE Padding. Absent renders no Margin row at all - a text
   * layer keeps Padding only (AC-11).
   */
  margin?: LayerPadding;
  onMarginChange?: (margin: LayerPadding) => void;
  /** One line of data text (an accessory's header, name or spec): no line height, no padding. */
  singleLine?: boolean;
}) {
  return (
    <>
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between">
          <Label className="text-xs text-muted-foreground">Font Family</Label>
          {onUploadFont && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-2xs"
              onClick={onUploadFont}
            >
              Manage fonts
            </Button>
          )}
        </div>
        <SearchableSelect
          value={values.fontFamily}
          onChange={(v: string) => onChange({ fontFamily: v })}
          options={fontOptions}
        />
      </div>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <NumberInput
            label="Font Size"
            value={values.fontSize}
            onChange={(v) => onChange({ fontSize: v })}
            step={0.5}
            min={4}
          />
        </div>
        <ToggleGroup
          type="multiple"
          variant="outline"
          size="sm"
          value={[
            values.fontWeight >= 600 && 'bold',
            values.italic && 'italic',
            values.underline && 'underline',
            values.strikethrough && 'strikethrough',
          ].filter((v): v is string => Boolean(v))}
          onValueChange={(next: string[]) => {
            const on = new Set(next);
            // Only rewrite fontWeight when Bold's OWN pressed state actually
            // changed - a `type="multiple"` group reports every currently
            // pressed item on every click, so toggling Italic while a 600+
            // weight reads Bold as pressed must not collapse that weight to
            // the canonical 700 as a side effect of a click nowhere near it.
            const wasBold = values.fontWeight >= 600;
            const willBeBold = on.has('bold');
            onChange({
              fontWeight:
                willBeBold === wasBold ? values.fontWeight : willBeBold ? 700 : 400,
              italic: on.has('italic'),
              underline: on.has('underline'),
              strikethrough: on.has('strikethrough'),
            });
          }}
        >
          <ToggleGroupItem value="bold" aria-label="Bold" title="Bold">
            <Bold className="size-3.5" />
          </ToggleGroupItem>
          <ToggleGroupItem value="italic" aria-label="Italic" title="Italic">
            <Italic className="size-3.5" />
          </ToggleGroupItem>
          <ToggleGroupItem value="underline" aria-label="Underline" title="Underline">
            <Underline className="size-3.5" />
          </ToggleGroupItem>
          <ToggleGroupItem value="strikethrough" aria-label="Strikethrough" title="Strikethrough">
            <Strikethrough className="size-3.5" />
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Font Weight</Label>
        <SearchableSelect
          value={String(values.fontWeight)}
          onChange={(v: string) => onChange({ fontWeight: parseInt(v, 10) })}
          options={FONT_WEIGHT_OPTIONS}
        />
      </div>
      <ColorPicker
        label={colourLabel}
        value={colour}
        onChange={onColourChange}
        usedColours={usedColours}
      />
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Align</Label>
        <div className="flex gap-1">
          {(['left', 'center', 'right'] as const).map((a) => (
            <button
              key={a}
              type="button"
              className={`flex-1 rounded border px-2 py-0.5 text-xs ${
                values.align === a
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-input hover:bg-accent'
              }`}
              onClick={() => onChange({ align: a })}
            >
              {a.charAt(0).toUpperCase() + a.slice(1)}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {!singleLine && (
          <NumberInput
            label="Line Height"
            value={values.lineHeight}
            onChange={(v) => onChange({ lineHeight: v })}
            step={0.1}
            min={0.5}
          />
        )}
        <NumberInput
          label="Letter Spacing"
          value={values.letterSpacing}
          onChange={(v) => onChange({ letterSpacing: v })}
          step={0.1}
        />
      </div>
      {margin && onMarginChange && (
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Margin (mm)</Label>
          <SidesInput value={margin} onChange={onMarginChange} />
        </div>
      )}
      {!singleLine && (
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Padding (mm)</Label>
          <SidesInput
            value={values.padding}
            onChange={(padding) => onChange({ padding })}
          />
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Shape inspector
// ---------------------------------------------------------------------------

/**
 * The shape select's write, with the polygon's corners seeded and dropped
 * alongside it (S4, AC-S4-1).
 *
 * Turning a rectangle into a polygon seeds the box's own four corners, so it
 * keeps looking exactly like the rectangle until a corner is moved; turning
 * it back drops them, so a later switch to polygon starts from the box again
 * rather than from corners the user cannot see.
 */
function withShape(
  props: Extract<TagLayerProps, { kind: 'shape' }>,
  shape: ShapeType,
): Extract<TagLayerProps, { kind: 'shape' }> {
  return {
    ...props,
    shape,
    // Explicitly undefined, not omitted: the caller MERGES this over the
    // layer's current props, so an omitted key would leave the old corners
    // in place.
    points: shape === 'polygon' ? (props.points ?? defaultPolygonPoints()) : undefined,
  };
}

function ShapeInspector({
  props,
  onChange,
  usedColours,
}: {
  props: Extract<TagLayerProps, { kind: 'shape' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
  usedColours: string[];
}) {
  return (
    <section>
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Shape
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Shape Type</Label>
          <SearchableSelect
            value={props.shape}
            onChange={(v: string) => onChange(withShape(props, v as ShapeType))}
            options={SHAPE_TYPE_OPTIONS}
          />
        </div>
        <ColorPicker
          label="Fill"
          value={props.fill}
          onChange={(v) => onChange({ ...props, fill: v })}
          usedColours={usedColours}
        />
        <ColorPicker
          label="Stroke"
          value={props.stroke}
          onChange={(v) => onChange({ ...props, stroke: v })}
          usedColours={usedColours}
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
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Image
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-2xs text-muted-foreground">{sourceLabel}</span>
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
        {/* Mirror in place (PRICETAG-DESIGNER-GAPS item 1): two toggles, so
            a tap photo can face the other way without a second upload. */}
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Flip</Label>
          {/* Stacked, full width: side by side the second label was cut off
              in the narrow inspector at 1280 px (crew browser pass, 5 Nov). */}
          <div className="flex flex-col gap-1">
            <Button
              type="button"
              variant={props.flipX ? 'secondary' : 'outline'}
              size="sm"
              className="h-7 w-full justify-start text-xs"
              aria-pressed={props.flipX === true}
              onClick={() => onChange({ ...props, flipX: !props.flipX })}
            >
              <FlipHorizontal2 className="size-3.5" />
              Flip horizontal
            </Button>
            <Button
              type="button"
              variant={props.flipY ? 'secondary' : 'outline'}
              size="sm"
              className="h-7 w-full justify-start text-xs"
              aria-pressed={props.flipY === true}
              onClick={() => onChange({ ...props, flipY: !props.flipY })}
            >
              <FlipVertical2 className="size-3.5" />
              Flip vertical
            </Button>
          </div>
        </div>
        {/* Only when a crop is actually set (S8, AC-S8-5) - entering crop
            mode itself is the context menu's "Crop image", not this panel. */}
        {isCropped(props.cropRect) && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => onChange({ ...props, cropRect: undefined })}
          >
            Reset crop
          </Button>
        )}
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
  usedColours,
  fontOptions,
  onUploadFont,
}: {
  props: Extract<TagLayerProps, { kind: 'price_badge' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
  usedColours: string[];
  fontOptions: SearchableSelectOption[];
  onUploadFont?: () => void;
}) {
  const typo = priceBadgeTypography(props);
  const insets = priceBadgeInsets(props);
  const hasMargin = props.margin != null;

  /**
   * Write a Margin edit (S3b, AC-6/10).
   *
   * The FIRST edit on a legacy badge (one with no `margin` yet) is what moves
   * it onto the new semantics: `padding` used to double as the callout's own
   * inset, so it resets to zero in the SAME update that writes `margin` - the
   * value the SidesInput just edited already carries the legacy padding on
   * every side it did not touch (it started from `insets.margin`), so the
   * callout does not jump (AC-10).
   */
  const writeMargin = (margin: LayerPadding) => {
    onChange(hasMargin ? { ...props, margin } : { ...props, margin, padding: ZERO_PADDING });
  };

  /**
   * Write a Padding edit (S3b, AC-6/10). Same first-edit rule as Margin: a
   * legacy badge seeds `margin` from whatever `padding` used to be, so the
   * callout stays put while the figure inset restarts at the value just typed.
   */
  const writePadding = (padding: LayerPadding) => {
    onChange(
      hasMargin ? { ...props, padding } : { ...props, margin: props.padding ?? ZERO_PADDING, padding },
    );
  };

  return (
    <section>
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
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
        {/* The promotional block is always boxed - the struck price above a
            filled box is what it IS (D26) - so the choice only exists for a
            list-only badge (AC-S6-1/3). */}
        {props.variant === 'list_only' && (
          <label className="flex items-center gap-1.5 text-xs">
            <Checkbox
              checked={props.showBox === true}
              onCheckedChange={(v) => onChange({ ...props, showBox: !!v })}
            />
            Box
          </label>
        )}
        <ColorPicker
          label="Box Fill"
          value={props.fill}
          onChange={(v) => onChange({ ...props, fill: v })}
          usedColours={usedColours}
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
        {/* Off, the figure and the promo lines drop `RM` (S3c, AC-13/14). On
            by default so a badge saved before this reads exactly as it did
            (AC-15). */}
        <label className="flex items-center gap-1.5 text-xs">
          <Checkbox
            checked={props.showCurrency ?? true}
            onCheckedChange={(v) => onChange({ ...props, showCurrency: !!v })}
          />
          Show currency
        </label>
        {/* The figure is text, and a designer sets text the same way wherever
            it is (S6b, AC-S6-4). An empty box means the badge has not named
            that field, so it keeps drawing the way it always did. */}
        <TypographyControls
          values={{
            fontFamily: typo.fontFamily ?? '',
            fontSize: typo.fontSize,
            // The figure has always been bold, so that is what an unnamed
            // weight reads as rather than a blank select.
            fontWeight: typo.fontWeight ?? 700,
            italic: typo.italic,
            underline: typo.underline,
            strikethrough: typo.strikethrough,
            align: typo.align,
            lineHeight: typo.lineHeight,
            letterSpacing: typo.letterSpacing,
            padding: insets.padding,
          }}
          onChange={(changes) => {
            if (changes.padding) {
              writePadding(changes.padding);
              return;
            }
            onChange({ ...props, ...changes });
          }}
          margin={insets.margin}
          onMarginChange={writeMargin}
          colour={props.textColor}
          colourLabel="Text Colour"
          onColourChange={(v) => onChange({ ...props, textColor: v })}
          usedColours={usedColours}
          fontOptions={fontOptions}
          onUploadFont={onUploadFont}
        />
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
 * A block also carries its own eye chip on the canvas itself, shown on hover
 * or select (D10, S6); this is the same action from the sidebar, for a
 * designer who already has the block selected and does not want to go
 * hunting for its outline.
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
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Preview
      </h4>
      {label ? (
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="min-w-0 flex-1 truncate text-left text-2xs font-medium hover:underline"
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
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Bound To
      </h4>
      {binding ? (
        <div className="flex flex-col gap-2">
          <p className="text-2xs font-medium">
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
        <p className="text-2xs text-muted-foreground">
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
// Show only when (PS-SPEC-SHEET)
// ---------------------------------------------------------------------------

/**
 * Two optional conditions, both must hold for the layer to print: the page has accessory N
 * (an accessory row, its frame and its photo), and the layer's product has a Yes spec (a
 * Rimless or Accessible badge). The canvas keeps drawing the layer either way.
 */
function ShowWhenInspector({
  layer,
  specKeys,
  onChange,
}: {
  layer: TagLayer;
  specKeys: SpecKeyOption[];
  onChange: (show_when: LayerShowWhen | null) => void;
}) {
  const partId = useId();
  const specId = useId();
  const when = layer.show_when ?? {};
  const set = (next: LayerShowWhen) => {
    const clean: LayerShowWhen = {};
    if (next.part != null) clean.part = next.part;
    if (next.spec) clean.spec = next.spec;
    onChange(Object.keys(clean).length ? clean : null);
  };
  const partOptions: SearchableSelectOption[] = [1, 2, 3].map((n) => ({
    value: String(n - 1),
    label: `Accessory ${n} exists`,
  }));
  const specOptions: SearchableSelectOption[] = specKeys.map((key) => ({
    value: key.key,
    label: `${key.label} is Yes`,
  }));
  return (
    <section>
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Show only when
      </h4>
      <div className="flex flex-col gap-2">
        <Label htmlFor={partId} className="sr-only">
          Accessory
        </Label>
        <SearchableSelect
          id={partId}
          size="sm"
          clearable
          placeholder="Any page"
          value={when.part != null ? String(when.part) : ''}
          onChange={(v: string) => set({ ...when, part: v === '' ? null : Number(v) })}
          options={partOptions}
        />
        <Label htmlFor={specId} className="sr-only">
          Spec
        </Label>
        <SearchableSelect
          id={specId}
          size="sm"
          clearable
          placeholder="Any product"
          value={when.spec ?? ''}
          onChange={(v: string) => set({ ...when, spec: v || null })}
          options={specOptions}
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Subject picker (D7/AC-S4-1)
// ---------------------------------------------------------------------------

/**
 * Which of a combo tag's products a layer reads. `-1` is the parent alone;
 * `0..n` is that part, in package order (`subjectParts`' own order). A price
 * badge alone also offers `Tag total` - absent `subjectPart` - since that is
 * what it always printed before this field existed (AC-S4-4).
 */
function SubjectInspector({
  props,
  parts,
  slots,
  parentCode,
  onChange,
}: {
  props: TagLayerProps;
  /** The request designer's line parts; absent in the template editor (positions instead). */
  parts?: TagPartData[];
  slots?: TagSlots | null;
  parentCode: string;
  onChange: (changes: Partial<TagLayerProps>) => void;
}) {
  const isPriceBadge = props.kind === 'price_badge';
  // A price badge defaults to the Tag total; an accessories box to the TAG's own list (the
  // combo's on a combo tag, card rule A3). Either way "no subject" is its own first option.
  const defaultLabel = isPriceBadge
    ? 'Tag total'
    : props.kind === 'accessories'
      ? "This tag's list (combo or product)"
      : null;
  // An accessories box names each choice as a LIST ("Main product's list"), so a pinned box is
  // not read as "the combo's list for this slot" (owner, 7 Nov). Wording only: values unchanged.
  const listOf = props.kind === 'accessories' ? accessoryListLabel : (label: string) => label;
  // Two inspectors can be mounted at once (a template editor beside the
  // request designer), and a hard-coded id makes the second `<label>` point
  // at the first one's select.
  const selectId = useId();
  const subjectPart =
    'subjectPart' in props && typeof props.subjectPart === 'number'
      ? props.subjectPart
      : undefined;
  const subjectSlot = 'subjectSlot' in props ? props.subjectSlot : undefined;
  // r10 S6 (AC-S6-4): a tag's parts now carry every candidate of every
  // choice group, not only the one this tag chose, so the list is grouped
  // under the group's role ("Kitchen Tap") once any part carries one, and
  // this tag's own candidate says so. A row without roles - a fixed part, or
  // a row pinned before r10 - renders the same flat list it always did.
  const grouped = (parts ?? []).some((part) => Boolean(part.role));
  const options: SearchableSelectOption[] = parts
    ? [
        ...(defaultLabel ? [{ value: 'default', label: defaultLabel }] : []),
        { value: '-1', label: listOf(parentCode || 'Parent') },
        ...parts.map((part, index) => ({
          value: String(index),
          label: `${listOf(part.code || part.name)}${part.chosen ? ' (this tag)' : ''}`,
          ...(grouped && part.role ? { group: part.role } : {}),
        })),
      ]
    : [
        // A layer saved with a part number keeps showing it, so it stays visible and replaceable.
        ...(!subjectSlot && subjectPart !== undefined
          ? [{ value: String(subjectPart), label: listOf(`Part ${subjectPart + 1}`) }]
          : []),
        ...slotOptions(slots, defaultLabel, listOf),
      ];
  const value = parts
    ? subjectPart === undefined
      ? defaultLabel
        ? 'default'
        : '-1'
      : String(subjectPart)
    : subjectSlot
      ? slotValue(subjectSlot)
      : subjectPart !== undefined
        ? String(subjectPart)
        : defaultLabel
          ? 'default'
          : 'slot:main';
  return (
    <section>
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Product
      </h4>
      {/* `htmlFor`/`id` is what actually pairs a `<label>` with its control
       *  (unlike the `<h4>` heading above, a section title every sibling
       *  inspector section uses) - `sr-only` since the heading already
       *  says "Product" visually, one word away. */}
      <Label htmlFor={selectId} className="sr-only">
        Product
      </Label>
      <SearchableSelect
        id={selectId}
        size="sm"
        value={value}
        onChange={(v: string) => {
          // A position and a part number are two ways to say the same thing, and the
          // position wins at read time, so choosing either clears the other.
          const slot = parseSlotValue(v);
          onChange({
            subjectSlot: slot,
            subjectPart: slot || v === 'default' ? undefined : Number(v),
          } as Partial<TagLayerProps>);
        }}
        options={options}
      />
    </section>
  );
}

function slotValue(slot: SubjectSlot): string {
  switch (slot.kind) {
    case 'main':
      return 'slot:main';
    case 'fixed':
      return `slot:fixed:${slot.index}`;
    case 'pick':
      return `slot:pick:${slot.group}:${slot.index}`;
    case 'upgrade':
      return `slot:upgrade:${slot.index}`;
  }
}

function parseSlotValue(value: string): SubjectSlot | undefined {
  const [prefix, kind, a, b] = value.split(':');
  if (prefix !== 'slot') return undefined;
  if (kind === 'main') return { kind: 'main' };
  if (kind === 'fixed') return { kind: 'fixed', index: Number(a) };
  if (kind === 'pick') return { kind: 'pick', group: Number(a), index: Number(b) };
  if (kind === 'upgrade') return { kind: 'upgrade', index: Number(a) };
  return undefined;
}

/** The positions a layer may read: the previewed combo's own, else the generic set. */
/**
 * An accessories box's option for one product: "Main product" reads "Main product's list", any
 * other name "<name> product's list" ("Fixed part 1 product's list", "SRTW5000 product's list").
 */
export function accessoryListLabel(label: string): string {
  return /\bproduct$/i.test(label) ? `${label}'s list` : `${label} product's list`;
}

function slotOptions(
  slots: TagSlots | null | undefined,
  defaultLabel: string | null,
  listOf: (label: string) => string = (label) => label,
): SearchableSelectOption[] {
  const out: SearchableSelectOption[] = [];
  const add = (slot: SubjectSlot, code?: string, group?: string) =>
    out.push({
      value: slotValue(slot),
      label: listOf(slotLabel(slot, slots)),
      ...(code ? { description: code } : {}),
      ...(group ? { group } : {}),
    });
  if (defaultLabel) out.push({ value: 'default', label: defaultLabel });
  add({ kind: 'main' });
  for (const position of comboPositions(slots)) add(position.slot, position.code, position.group);
  return out;
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
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
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
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Badge
      </h4>
      <div className="flex items-center justify-between gap-2">
        <span className="text-2xs text-muted-foreground">
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

// ---------------------------------------------------------------------------
// Barcode inspector (D18, S7)
// ---------------------------------------------------------------------------

function BarcodeInspector({
  layer,
  props,
  onChange,
  onUpdate,
  resolvedText,
}: {
  layer: TagLayer;
  props: Extract<TagLayerProps, { kind: 'barcode' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
  onUpdate: (changes: Partial<TagLayer>) => void;
  resolvedText: string | null;
}) {
  // Same pattern as the text layer's `text_override` (D23): the barcode
  // layer is always bound to slot 'barcode', so an override here works the
  // same way - value in, binding survives, Relink clears it again. The
  // product master stays the source of truth; the override lives in the doc
  // only.
  //
  // An EMPTY override is still an override (S5): `''` is not `null`, so
  // clearing the box does not fall back to the product's barcode the way
  // `null` does - only Relink does that. Before this an empty string was
  // coerced to `null` on the way out, so deleting the text and typing
  // something new snapped straight back to the product value every time.
  const overridden = layer.text_override != null;
  const shown = layer.text_override ?? resolvedText ?? '';

  return (
    <section>
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Barcode
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">Barcode value</Label>
            {overridden && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 px-1.5 text-2xs"
                onClick={() => onUpdate({ text_override: null })}
              >
                <Link2 className="mr-1 size-3" />
                Relink
              </Button>
            )}
          </div>
          <Input
            value={shown}
            placeholder={resolvedText ?? 'No barcode on the product'}
            onChange={(e) => onUpdate({ text_override: e.target.value })}
          />
          {overridden && (
            <span className="flex items-center gap-1 text-2xs text-amber-600">
              <Link2Off className="size-3" />
              Unlinked from product data
            </span>
          )}
        </div>
        <label className="flex items-center gap-1.5 text-xs">
          <Checkbox
            checked={props.show_code}
            onCheckedChange={(v) => onChange({ ...props, show_code: !!v })}
          />
          Show product code
        </label>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Feature icons inspector (PRICETAG-DESIGNER-GAPS item 3)
// ---------------------------------------------------------------------------

const FEATURE_ICON_ALIGNS: { value: FeatureIconsLayerProps['align']; label: string }[] = [
  { value: 'left', label: 'Left' },
  { value: 'center', label: 'Centre' },
  { value: 'right', label: 'Right' },
];

/**
 * Icon size, spacing and alignment, plus the icon library (upload / rename). The order of the
 * icons is the spec registry's (each spec's Icon order), never the layer's. Every write carries
 * the whole props object, so a change never drops the subject.
 */
/**
 * PRICETAG-ACCESSORIES: the box's own look, every part of it set per box (owner hand test,
 * 6 Nov ~15:00: "too rigid, too hard coded"). Item layout (picture above or left of the text),
 * frame on/off, header shown/hidden/on the border, the "+" badge on/off, and the header, name and
 * spec text set with the SAME TypographyControls a text layer uses. Warns when the previewed list
 * does not fit (A6).
 */
function AccessoriesInspector({
  props,
  fit,
  boxWidth_mm,
  boxHeight_mm,
  usedColours,
  fontOptions,
  onUploadFont,
  onChange,
}: {
  props: AccessoriesLayerProps;
  fit?: { count: number; lines: number };
  boxWidth_mm: number;
  boxHeight_mm: number;
  usedColours: string[];
  fontOptions: SearchableSelectOption[];
  onUploadFont?: () => void;
  onChange: (changes: Partial<AccessoriesLayerProps>) => void;
}) {
  const headerId = useId();
  const dropped = fit
    ? accessoryBoxLayout(fit.count, props, boxWidth_mm, boxHeight_mm, fit.lines).dropped
    : 0;
  const showHeader = props.showHeader !== false;
  const showFrame = props.showFrame !== false;
  const itemLayout = itemLayoutOf(props);

  /** One text role's TypographyControls: size and colour live on their own props. */
  const textRole = (
    title: string,
    styleKey: 'headerStyle' | 'nameStyle' | 'specStyle',
    sizeKey: 'headerFontSize' | 'nameFontSize' | 'specFontSize',
    resolved: AccessoryLineStyle,
    onColour: (value: string) => void,
  ) => (
    <section className="flex flex-col gap-2">
      <h5 className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">{title}</h5>
      <TypographyControls
        singleLine
        values={{
          fontFamily: resolved.fontFamily ?? '',
          fontSize: props[sizeKey],
          fontWeight: resolved.fontWeight,
          italic: resolved.italic,
          underline: resolved.underline,
          strikethrough: resolved.strikethrough,
          align: resolved.align,
          lineHeight: null,
          letterSpacing: resolved.letterSpacing,
          padding: ZERO_PADDING,
        }}
        onChange={(changes) => {
          // Line height and padding are not offered (singleLine); size lives on its own prop.
          const { fontSize, fontFamily, fontWeight, italic, underline, strikethrough, align, letterSpacing } =
            changes;
          const style = Object.fromEntries(
            Object.entries({ fontFamily, fontWeight, italic, underline, strikethrough, align, letterSpacing })
              .filter(([, value]) => value !== undefined),
          );
          const next: Partial<AccessoriesLayerProps> = {
            [styleKey]: { ...(props[styleKey] ?? {}), ...style },
          };
          if (fontSize !== undefined) next[sizeKey] = fontSize;
          onChange(next);
        }}
        colour={resolved.color}
        onColourChange={onColour}
        usedColours={usedColours}
        fontOptions={fontOptions}
        onUploadFont={onUploadFont}
      />
    </section>
  );

  return (
    <section className="flex flex-col gap-3">
      <h4 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Accessories
      </h4>

      {/* Layout */}
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Direction</Label>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={props.direction}
          onValueChange={(next: string) => {
            if (next) onChange({ direction: next as AccessoriesLayerProps['direction'] });
          }}
        >
          <ToggleGroupItem value="vertical" className="flex-1 text-xs">
            Vertical
          </ToggleGroupItem>
          <ToggleGroupItem value="horizontal" className="flex-1 text-xs">
            Horizontal
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Item layout</Label>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={itemLayout}
          onValueChange={(next: string) => {
            if (next) onChange({ itemLayout: next as 'stacked' | 'side' });
          }}
        >
          <ToggleGroupItem value="stacked" className="flex-1 text-xs">
            Picture above text
          </ToggleGroupItem>
          <ToggleGroupItem value="side" className="flex-1 text-xs">
            Picture left of text
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <NumberInput
          label="Picture size (mm)"
          value={props.imageSize_mm}
          onChange={(v) => onChange({ imageSize_mm: v })}
          step={0.5}
          min={0}
          max={100}
        />
        <NumberInput
          label="Gap (mm)"
          value={props.gap_mm}
          onChange={(v) => onChange({ gap_mm: v })}
          step={0.5}
          min={0}
          max={50}
        />
        {props.direction === 'horizontal' && (
          <NumberInput
            label="Card width (mm)"
            value={props.cardWidth_mm}
            onChange={(v) => onChange({ cardWidth_mm: v })}
            step={0.5}
            min={5}
            max={300}
          />
        )}
        <ColorPicker
          label="Card fill"
          value={props.cardFill}
          onChange={(v) => onChange({ cardFill: v })}
          usedColours={usedColours}
        />
      </div>

      {/* Frame */}
      <label className="flex items-center gap-1.5 text-xs">
        <Checkbox
          checked={showFrame}
          onCheckedChange={(v) => onChange({ showFrame: !!v })}
          aria-label="Show frame"
        />
        Show frame
      </label>
      {showFrame && (
        <div className="grid grid-cols-2 gap-2">
          <ColorPicker
            label="Box fill"
            value={props.fill}
            onChange={(v) => onChange({ fill: v })}
            usedColours={usedColours}
          />
          <ColorPicker
            label="Border colour"
            value={props.stroke}
            onChange={(v) => onChange({ stroke: v })}
            usedColours={usedColours}
          />
          <NumberInput
            label="Border (mm)"
            value={props.strokeWidth_mm}
            onChange={(v) => onChange({ strokeWidth_mm: v })}
            step={0.1}
            min={0}
            max={5}
          />
          <NumberInput
            label="Corner radius (mm)"
            value={props.cornerRadius_mm}
            onChange={(v) => onChange({ cornerRadius_mm: v })}
            step={0.5}
            min={0}
            max={50}
          />
        </div>
      )}

      {/* Header */}
      <label className="flex items-center gap-1.5 text-xs">
        <Checkbox
          checked={showHeader}
          onCheckedChange={(v) => onChange({ showHeader: !!v })}
          aria-label="Show header"
        />
        Show header
      </label>
      {showHeader && (
        <>
          <div className="flex flex-col gap-1">
            <Label htmlFor={headerId} className="text-xs text-muted-foreground">
              Header text
            </Label>
            <Input
              id={headerId}
              className="h-7 px-2 text-xs"
              value={props.headerText}
              maxLength={60}
              onChange={(e) => onChange({ headerText: e.target.value })}
            />
          </div>
          {showFrame && (
            <label className="flex items-center gap-1.5 text-xs">
              <Checkbox
                checked={Boolean(props.headerOnBorder)}
                onCheckedChange={(v) => onChange({ headerOnBorder: !!v })}
                aria-label="Header on the border"
              />
              Header on the border
            </label>
          )}
          {showFrame && props.headerOnBorder && (
            <ColorPicker
              label="Behind the header"
              value={props.headerBackground || '#ffffff'}
              onChange={(v) => onChange({ headerBackground: v })}
              usedColours={usedColours}
            />
          )}
          {textRole('Header text style', 'headerStyle', 'headerFontSize', accessoryHeaderStyle(props), (v) =>
            onChange({ headerColor: v }),
          )}
        </>
      )}

      {/* Name and spec */}
      {textRole('Name text', 'nameStyle', 'nameFontSize', accessoryLineStyle(props, 0), (v) =>
        onChange({ nameStyle: { ...(props.nameStyle ?? {}), color: v } }),
      )}
      {textRole('Spec text', 'specStyle', 'specFontSize', accessoryLineStyle(props, 1), (v) =>
        onChange({ specStyle: { ...(props.specStyle ?? {}), color: v } }),
      )}

      {/* Badge */}
      <label className="flex items-center gap-1.5 text-xs">
        <Checkbox
          checked={props.showBadge}
          onCheckedChange={(v) => onChange({ showBadge: !!v })}
          aria-label="Show the plus badge"
        />
        Show &quot;+&quot; badge
      </label>
      {props.showBadge && (
        <ColorPicker
          label="Badge colour"
          value={props.badgeColor}
          onChange={(v) => onChange({ badgeColor: v })}
          usedColours={usedColours}
        />
      )}

      {dropped > 0 && fit && (
        <Alert variant="warning" size="sm" role="status">
          <AlertDescription>
            {dropped} of {fit.count} accessories do not fit this box. Make the box bigger or the cards
            smaller.
          </AlertDescription>
        </Alert>
      )}
    </section>
  );
}

function FeatureIconsInspector({
  props,
  onManageIcons,
  iconCount,
  boxWidth_mm,
  onChange,
}: {
  props: FeatureIconsLayerProps;
  onManageIcons?: () => void;
  /** Icons the previewed product reads; 0 with nothing previewed. */
  iconCount: number;
  boxWidth_mm: number;
  onChange: (changes: Partial<FeatureIconsLayerProps>) => void;
}) {
  // Icons that do not fit the box are not drawn (print cannot draw outside it): say so.
  const { dropped } = featureIconFit(iconCount, props, boxWidth_mm);
  return (
    <section className="flex flex-col gap-2">
      <h4 className="text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
        Feature icons
      </h4>
      <div className="grid grid-cols-2 gap-2">
        <NumberInput
          label="Icon size (mm)"
          value={props.iconSize_mm}
          onChange={(v) => onChange({ iconSize_mm: v })}
          step={0.5}
          min={0.5}
          max={200}
        />
        <NumberInput
          label="Spacing (mm)"
          value={props.gap_mm}
          onChange={(v) => onChange({ gap_mm: v })}
          step={0.5}
          min={0}
          max={100}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Align</Label>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={props.align}
          onValueChange={(next: string) => {
            // A single group reports '' when the pressed item is clicked again: keep the alignment.
            if (next) onChange({ align: next as FeatureIconsLayerProps['align'] });
          }}
        >
          {FEATURE_ICON_ALIGNS.map((a) => (
            <ToggleGroupItem key={a.value} value={a.value} className="flex-1 text-xs">
              {a.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      {dropped > 0 && (
        <Alert variant="warning" size="sm" role="status">
          <AlertDescription>
            {dropped} of {iconCount} icons do not fit this box. Widen the box or make the icons smaller.
          </AlertDescription>
        </Alert>
      )}
      {onManageIcons && (
        <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={onManageIcons}>
          Manage icons
        </Button>
      )}
    </section>
  );
}

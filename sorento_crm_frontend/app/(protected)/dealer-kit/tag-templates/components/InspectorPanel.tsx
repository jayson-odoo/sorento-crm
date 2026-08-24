'use client';

/**
 * Right sidebar property inspector for the selected layer.
 *
 * Common props: position (x/y mm), size (w/h mm), rotation, locked, visible.
 * Type-specific sections render below based on `layer.props.kind`.
 */

import { useCallback } from 'react';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type {
  ImageFit,
  PriceDisplayType,
  ShapeType,
  SlotBinding,
  TagLayer,
  TagLayerProps,
} from '@/lib/dealer-kit/tag-template-types';
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

const FONT_FAMILY_OPTIONS = [
  { value: 'DM Sans', label: 'DM Sans' },
  { value: 'Inter', label: 'Inter' },
  { value: 'Arial', label: 'Arial' },
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
}

export function InspectorPanel({ layer, onUpdate, onUpdateProps }: InspectorPanelProps) {
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

          {/* -- Type-specific props -- */}
          {layer.props.kind === 'text' && (
            <TextInspector props={layer.props} onChange={updateProps} />
          )}
          {layer.props.kind === 'shape' && (
            <ShapeInspector props={layer.props} onChange={updateProps} />
          )}
          {layer.props.kind === 'image' && (
            <ImageInspector props={layer.props} onChange={updateProps} />
          )}
          {layer.props.kind === 'price_field' && (
            <PriceFieldInspector props={layer.props} onChange={updateProps} />
          )}
          {layer.props.kind === 'product_slot' && (
            <ProductSlotInspector props={layer.props} onChange={updateProps} />
          )}
          {layer.props.kind === 'badge' && (
            <BadgeInspector props={layer.props} onChange={updateProps} />
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
  props,
  onChange,
}: {
  props: Extract<TagLayerProps, { kind: 'text' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
}) {
  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Text
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Content</Label>
          <textarea
            className="min-h-[60px] w-full rounded-md border bg-background px-2 py-1 text-xs"
            value={props.text}
            onChange={(e) => onChange({ ...props, text: e.target.value })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Font Family</Label>
          <SearchableSelect
            value={props.fontFamily}
            onChange={(v: string) => onChange({ ...props, fontFamily: v })}
            options={FONT_FAMILY_OPTIONS}
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
  props,
  onChange,
}: {
  props: Extract<TagLayerProps, { kind: 'image' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
}) {
  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Image
      </h4>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Fit</Label>
          <SearchableSelect
            value={props.fit}
            onChange={(v: string) => onChange({ ...props, fit: v as ImageFit })}
            options={IMAGE_FIT_OPTIONS}
          />
        </div>
        <p className="text-[10px] text-muted-foreground">
          Asset: {props.assetId || '(none)'}
        </p>
      </div>
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
  props,
}: {
  props: Extract<TagLayerProps, { kind: 'badge' }>;
  onChange: (changes: Partial<TagLayerProps>) => void;
}) {
  return (
    <section>
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Badge
      </h4>
      <p className="text-[10px] text-muted-foreground">
        Asset: {props.assetId || '(none)'}
      </p>
      <p className="mt-1 text-[10px] text-muted-foreground">
        Badge/icon library picker is coming in S4.
      </p>
    </section>
  );
}

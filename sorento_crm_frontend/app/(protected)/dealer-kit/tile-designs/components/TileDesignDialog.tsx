'use client';

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowDown, ArrowUp } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ProductTile } from '../../components/TileGrid';
import {
  TILE_FIELDS,
  createTileTemplate,
  updateTileTemplate,
} from '../../services/catalogueService';
import type { ResolvedTile, TileField, TileTemplate } from '@/lib/dealer-kit/types';

/**
 * Designing a tile.
 *
 * A tile design is an ordered list of the product fields a card shows. Order
 * matters, so it is editable - "price above the name" is a real design decision
 * and a checkbox list alone cannot express it.
 *
 * The preview is the point. A Designer is choosing what a customer sees, and a
 * list of field names is not that. It renders through the SAME `ProductTile`
 * the catalogue and the PDF use, against a stand-in product, so what is shown
 * here is what will be printed.
 */

/** A stand-in product, so the preview has something to draw. */
const SAMPLE: ResolvedTile = {
  productId: 'sample',
  productCode: 'SK-3040',
  productName: 'Undermount Kitchen Sink 760mm',
  price: 'RM 1,290.00',
  // On promotion on purpose: the offer treatment is the decision being made in
  // this dialog, and a sample with no offer would hide it.
  offerPrice: 'RM 899.00',
  invoicePrice: null,
  imageUrl: null,
  dimensions: '760 x 440 x 220 mm',
  badges: ['SIRIM'],
};

export function TileDesignDialog({
  open,
  onOpenChange,
  template,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Null creates a new design. */
  template: TileTemplate | null;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [fields, setFields] = useState<TileField[]>(['image', 'name', 'code', 'price']);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(template?.name ?? '');
    setFields(
      template?.fields?.length ? [...template.fields] : ['image', 'name', 'code', 'price'],
    );
  }, [open, template]);

  const toggle = (field: TileField) => {
    setFields((current) =>
      current.includes(field)
        ? current.filter((candidate) => candidate !== field)
        : [...current, field],
    );
  };

  const move = (field: TileField, direction: -1 | 1) => {
    setFields((current) => {
      const index = current.indexOf(field);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const save = async () => {
    if (!name.trim() || fields.length === 0) return;
    setSaving(true);
    try {
      if (template) {
        await updateTileTemplate(template.id, name.trim(), fields);
      } else {
        await createTileTemplate(name.trim(), fields);
      }
      await queryClient.invalidateQueries({ queryKey: ['dealer-kit', 'tile-templates'] });
      toast.success(template ? 'Tile design updated' : 'Tile design created');
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save this design.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{template ? 'Edit tile design' : 'New tile design'}</DialogTitle>
          <DialogDescription>
            Choose what each product card shows, and the order it shows it in. The preview is
            the real tile, so this is exactly how it prints.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-2">
          <Label htmlFor="dk-design-name" className="text-xs">
            Name
          </Label>
          <Input
            id="dk-design-name"
            value={name}
            placeholder="Standard product tile"
            onChange={(event) => setName(event.target.value)}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium text-foreground">Shown, in this order</p>

            {fields.length === 0 && (
              <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
                Nothing selected. A tile has to show at least one thing.
              </p>
            )}

            {fields.map((field, index) => {
              const meta = TILE_FIELDS.find((candidate) => candidate.value === field);
              return (
                <div
                  key={field}
                  className="flex items-center gap-2 rounded-md border border-border px-2 py-1.5"
                >
                  <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                    {index + 1}. {meta?.label ?? field}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Move ${meta?.label ?? field} up`}
                    disabled={index === 0}
                    onClick={() => move(field, -1)}
                  >
                    <ArrowUp className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Move ${meta?.label ?? field} down`}
                    disabled={index === fields.length - 1}
                    onClick={() => move(field, 1)}
                  >
                    <ArrowDown className="size-3.5" />
                  </Button>
                </div>
              );
            })}

            <p className="mt-2 text-xs font-medium text-foreground">Available</p>
            {TILE_FIELDS.filter((field) => !fields.includes(field.value)).map((field) => (
              <label
                key={field.value}
                className="flex cursor-pointer items-start gap-2 rounded-md border border-border px-2 py-1.5"
              >
                <Checkbox
                  checked={false}
                  aria-label={`Show ${field.label}`}
                  onCheckedChange={() => toggle(field.value)}
                />
                <span className="min-w-0">
                  <span className="block text-xs text-foreground">{field.label}</span>
                  <span className="block text-[10px] text-muted-foreground">{field.hint}</span>
                </span>
              </label>
            ))}
          </div>

          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium text-foreground">Preview</p>
            <div className="rounded-lg border border-border bg-muted/30 p-4">
              <div className="mx-auto max-w-[200px]" data-dk-design-preview>
                <ProductTile tile={SAMPLE} fields={fields} />
              </div>
            </div>
            <p className="text-[10px] text-muted-foreground">
              Shown with a sample product that is on promotion. Price is whatever the reader is
              allowed to see, so a consumer and a dealer can see different figures in the same
              design, and a product with no offer prints its list price on its own.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!name.trim() || fields.length === 0 || saving} onClick={save}>
            {saving ? 'Saving' : 'Save design'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

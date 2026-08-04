'use client';

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { GripVertical, Undo2, X } from 'lucide-react';

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
import { Sortable, SortableItem, SortableItemHandle } from '@/components/ui/sortable';
import {
  canUndo,
  newHistory,
  pushHistory,
  undo as undoHistory,
  type History,
} from '@/lib/dealer-kit/history';
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
 * The order is changed by DRAGGING, using the same `Sortable` the routing rules
 * and the column panel use. It was a pair of up/down arrows, which is a way of
 * expressing "move this to third" one click at a time while everything shuffles
 * under you - and it was the only reordering interaction in the system that did
 * not match the rest of it.
 *
 * Every change is undoable. Adding a field, dropping one, or reordering is a
 * design decision somebody is trying out, and trying something out is only free
 * if putting it back is one click.
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

const DEFAULT_FIELDS: TileField[] = ['image', 'name', 'code', 'price'];

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
  const [saving, setSaving] = useState(false);

  /**
   * The field list, with every step it has been through.
   *
   * Held as a history rather than a plain value because "I added Dimensions and
   * now I want it back how it was" had no answer: the only way out was to
   * remember what had been there and rebuild it by hand. The same `history`
   * helper the room designer uses.
   *
   * The NAME is deliberately not in here. Undo is for the design decisions, and
   * a text field that undoes a keystroke at a time behaves like nothing else on
   * the page.
   */
  const [history, setHistory] = useState<History<TileField[]>>(() => newHistory(DEFAULT_FIELDS));
  const fields = history.present;

  useEffect(() => {
    if (!open) return;
    setName(template?.name ?? '');
    // A fresh history per opening: undoing into the design you were editing
    // BEFORE this one would be a change nobody asked for.
    setHistory(newHistory(template?.fields?.length ? [...template.fields] : DEFAULT_FIELDS));
  }, [open, template]);

  /** Record a new field list as one undoable step. */
  const commit = (next: TileField[]) => setHistory((current) => pushHistory(current, next));

  const add = (field: TileField) => {
    if (fields.includes(field)) return;
    commit([...fields, field]);
  };

  const remove = (field: TileField) => commit(fields.filter((candidate) => candidate !== field));

  const labelOf = (field: TileField) =>
    TILE_FIELDS.find((candidate) => candidate.value === field)?.label ?? field;

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

  const available = TILE_FIELDS.filter((field) => !fields.includes(field.value));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{template ? 'Edit tile design' : 'New tile design'}</DialogTitle>
          <DialogDescription>
            Choose what each product card shows, and drag to set the order. The preview is the
            real tile, so this is exactly how it prints.
          </DialogDescription>
        </DialogHeader>

        {/* gap-6 between the sections and gap-3 inside them. It was gap-2
            throughout, which put a checkbox row the same distance from the row
            below it as from the heading of the next group - so the groups read
            as one long list. */}
        <div className="flex flex-col gap-6">
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

          <div className="grid gap-6 sm:grid-cols-2">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-medium text-foreground">Shown, in this order</p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={!canUndo(history)}
                  onClick={() => setHistory((current) => undoHistory(current))}
                  data-dk-design-undo
                >
                  <Undo2 className="size-3.5" />
                  Undo
                </Button>
              </div>

              {fields.length === 0 && (
                <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
                  Nothing selected. A tile has to show at least one thing.
                </p>
              )}

              {/* The same Sortable the routing rules and the column panel use,
                  so reordering behaves identically everywhere in the system. */}
              <Sortable
                value={fields}
                onValueChange={(next) => commit(next as TileField[])}
                getItemValue={(field) => field}
                strategy="vertical"
              >
                <div className="flex flex-col gap-2" data-dk-design-fields>
                  {fields.map((field, index) => (
                    <SortableItem key={field} value={field}>
                      <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-2">
                        <SortableItemHandle aria-label={`Drag ${labelOf(field)} to reorder`}>
                          <GripVertical className="size-4 text-muted-foreground" />
                        </SortableItemHandle>
                        <span className="w-4 shrink-0 text-xs text-muted-foreground">
                          {index + 1}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                          {labelOf(field)}
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="size-6 shrink-0 p-0"
                          aria-label={`Remove ${labelOf(field)}`}
                          onClick={() => remove(field)}
                        >
                          <X className="size-3.5" />
                        </Button>
                      </div>
                    </SortableItem>
                  ))}
                </div>
              </Sortable>

              {available.length > 0 && (
                <>
                  <p className="mt-1 text-xs font-medium text-foreground">Available</p>
                  <div className="flex flex-col gap-2">
                    {available.map((field) => (
                      <label
                        key={field.value}
                        className="flex cursor-pointer items-start gap-2 rounded-md border border-border px-2 py-2"
                      >
                        <Checkbox
                          checked={false}
                          aria-label={`Show ${field.label}`}
                          onCheckedChange={() => add(field.value)}
                        />
                        <span className="min-w-0">
                          <span className="block text-xs text-foreground">{field.label}</span>
                          <span className="block text-xs text-muted-foreground">{field.hint}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="flex flex-col gap-3">
              <p className="text-xs font-medium text-foreground">Preview</p>
              <div className="rounded-lg border border-border bg-muted/30 p-4">
                <div className="mx-auto max-w-[200px]" data-dk-design-preview>
                  <ProductTile tile={SAMPLE} fields={fields} />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Shown with a sample product that is on promotion. Price is whatever the reader is
                allowed to see, so a consumer and a dealer can see different figures in the same
                design, and a product with no offer prints its list price on its own.
              </p>
            </div>
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

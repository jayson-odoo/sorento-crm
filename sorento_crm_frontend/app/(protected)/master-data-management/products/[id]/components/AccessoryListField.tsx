'use client';

import { useRef, useState } from 'react';
import { GripVertical, Pencil, X } from 'lucide-react';
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { restrictToParentElement, restrictToVerticalAxis } from '@dnd-kit/modifiers';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { AttachmentImage } from '@/components/common/AttachmentImage';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { formatCurrency } from '@/lib/helpers';
import { richOneLine } from '@/lib/dealer-kit/rich-text';
import { codeWithName } from '@/lib/product-display';
import { getProducts } from '../../services/productService';
import { searchAccessories } from '../../../accessories/services/accessoryService';
import {
  useCreateAccessory,
  useOwnerAccessories,
  useReplaceOwnerAccessories,
} from '../../../accessories/hooks/useAccessories';
import {
  entryKey,
  hasOverrides,
  rowPicture,
  type AccessoryEntry,
  type AccessoryOwnerKind,
} from '../../../accessories/types/accessory.types';
import { AccessoryEntryDialog } from './AccessoryEntryDialog';

function AccessoryThumb({ accessory }: { accessory: AccessoryEntry }) {
  // The row's own pick (`entry.image_id`), so a Save shows it at once through the optimistic write.
  const picture = rowPicture(accessory);
  return (
    <AttachmentImage
      thumbUrl={picture?.thumb_url}
      url={picture?.url}
      className="size-10 shrink-0 rounded-md border object-cover"
      fallback={
        <span className="flex size-10 shrink-0 items-center justify-center rounded-md border border-dashed px-0.5 text-center text-2xs leading-tight text-muted-foreground">
          No picture
        </span>
      }
    />
  );
}

function AccessoryText({ accessory }: { accessory: AccessoryEntry }) {
  return (
    <div className="min-w-0 flex-1">
      <p className="truncate text-sm" title={accessory.name}>
        {accessory.kind === 'product' && accessory.code ? (
          <span className="font-semibold">{accessory.code} </span>
        ) : null}
        <span className={accessory.kind === 'product' ? '' : 'font-medium'}>{accessory.name}</span>
        {hasOverrides(accessory) ? (
          <Badge variant="secondary" size="sm" className="ml-1.5 align-middle">
            Own text
          </Badge>
        ) : null}
      </p>
      {accessory.kind === 'product' && accessory.list_price != null ? (
        <p className="truncate text-xs text-muted-foreground">
          LP: {formatCurrency(accessory.list_price)}
        </p>
      ) : null}
      {richOneLine(accessory.spec) ? (
        <p className="truncate text-xs text-muted-foreground" title={richOneLine(accessory.spec)}>
          {richOneLine(accessory.spec)}
        </p>
      ) : null}
    </div>
  );
}

const PRODUCT_PAGE_SIZE = 50;

function SortableRow({
  accessory,
  onRemove,
  onEdit,
}: {
  accessory: AccessoryEntry;
  onRemove: () => void;
  onEdit: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: entryKey(accessory),
  });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex items-center gap-2 rounded-md border bg-background p-2 ${isDragging ? 'z-10 shadow-md' : ''}`}
    >
      <button
        type="button"
        className="shrink-0 cursor-grab touch-none text-muted-foreground"
        aria-label={`Reorder ${accessory.name}`}
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-4" />
      </button>
      <AccessoryThumb accessory={accessory} />
      <AccessoryText accessory={accessory} />
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="shrink-0"
        aria-label="Edit for this list"
        onClick={onEdit}
      >
        <Pencil className="size-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="shrink-0"
        aria-label={`Remove ${accessory.name}`}
        onClick={onRemove}
      >
        <X className="size-4" />
      </Button>
    </li>
  );
}

/**
 * The ordered accessories of one product or one combo (PRICETAG-ACCESSORIES B1/B2).
 * Every change - add, remove, drag - saves at once as the whole ordered id list, optimistic
 * with a revert when the server refuses. Read-only when the reader cannot edit products.
 */
export function AccessoryListField({
  kind,
  ownerId,
  label,
  canEdit,
  hideLabel = false,
  ownerHostId,
}: {
  kind: AccessoryOwnerKind;
  ownerId: string;
  label?: string;
  canEdit: boolean;
  hideLabel?: boolean;
  /** The product that hosts this list, which cannot list itself. */
  ownerHostId?: string;
}) {
  const { data } = useOwnerAccessories(kind, ownerId);
  const save = useReplaceOwnerAccessories(kind, ownerId);
  const create = useCreateAccessory();
  const items = data ?? [];
  const known = useRef(new Map<string, AccessoryEntry>());
  const [editing, setEditing] = useState<AccessoryEntry | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const write = (next: AccessoryEntry[]) => save.mutate({ next });

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = items.findIndex((a) => entryKey(a) === active.id);
    const to = items.findIndex((a) => entryKey(a) === over.id);
    if (from < 0 || to < 0) return;
    write(arrayMove(items, from, to));
  };

  const has = (key: string) => items.some((a) => entryKey(a) === key);

  /**
   * ONE picker for both kinds (owner 10 Nov): the accessory library on the first page, then the
   * catalogue products, server-searched and paged. Values carry the kind (`accessory:<id>`,
   * `product:<id>`), the same key the list itself uses.
   */
  const fetchOptions = async (query: string, pageIndex: number): Promise<SearchableSelectOption[]> => {
    const [accessories, products] = await Promise.all([
      pageIndex === 0 ? searchAccessories(query) : Promise.resolve([]),
      getProducts({
        pageIndex,
        pageSize: PRODUCT_PAGE_SIZE,
        sorting: [],
        searchQuery: query,
        status: 'active',
      }),
    ]);
    const accessoryOptions = accessories
      .filter((a) => !has(`accessory:${a.id}`))
      .map((a) => {
        known.current.set(`accessory:${a.id}`, { ...a, kind: 'accessory', code: null, list_price: null });
        return {
          value: `accessory:${a.id}`,
          label: a.name,
          description: richOneLine(a.spec) || undefined,
          group: 'Accessories',
        };
      });
    const productOptions = (products.data ?? [])
      .filter((p) => p.id !== ownerHostId && !has(`product:${p.id}`))
      .map((p) => {
        known.current.set(`product:${p.id}`, {
          kind: 'product',
          id: p.id,
          name: p.product_name,
          spec: null,
          image: null,
          product_count: 0,
          combo_count: 0,
          code: p.product_code,
          list_price: null,
        });
        return {
          value: `product:${p.id}`,
          label: codeWithName(p.product_code, p.product_name),
          searchText: `${p.product_code} ${p.product_name}`,
          // Still pickable, with the grey hint the other combo pickers use (owner 7 Nov).
          description: p.is_discontinued ? 'Discontinued' : undefined,
          group: 'Products',
        };
      });
    return [...accessoryOptions, ...productOptions];
  };

  const add = (key: string) => {
    const picked = known.current.get(key);
    if (picked && !has(key)) write([...items, picked]);
  };

  const onCreate = async (name: string) => {
    try {
      const created = await create.mutateAsync({ name });
      write([...items, { ...created, kind: 'accessory', code: null, list_price: null }]);
    } catch {
      // The hook has already said why (a duplicate name, say).
    }
  };

  return (
    <div className="space-y-1.5">
      {label && !hideLabel ? <Label>{label}</Label> : null}
      {items.length === 0 && !canEdit ? (
        <p className="text-sm text-muted-foreground">-</p>
      ) : null}
      {items.length > 0 ? (
        canEdit ? (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            modifiers={[restrictToVerticalAxis, restrictToParentElement]}
            onDragEnd={onDragEnd}
          >
            <SortableContext
              items={items.map(entryKey)}
              strategy={verticalListSortingStrategy}
            >
              <ul className="space-y-1.5" aria-label={label ?? 'Accessories'}>
                {items.map((accessory) => (
                  <SortableRow
                    key={entryKey(accessory)}
                    accessory={accessory}
                    onRemove={() => write(items.filter((a) => entryKey(a) !== entryKey(accessory)))}
                    onEdit={() => setEditing(accessory)}
                  />
                ))}
              </ul>
            </SortableContext>
          </DndContext>
        ) : (
          <ul className="space-y-1.5" aria-label={label ?? 'Accessories'}>
            {items.map((accessory) => (
              <li key={entryKey(accessory)} className="flex items-center gap-2 rounded-md border p-2">
                <AccessoryThumb accessory={accessory} />
                <AccessoryText accessory={accessory} />
              </li>
            ))}
          </ul>
        )
      ) : null}
      <AccessoryEntryDialog
        entry={editing}
        onOpenChange={(open) => !open && setEditing(null)}
        onSave={(overrides) => {
          if (!editing) return;
          write(items.map((a) => (entryKey(a) === entryKey(editing) ? { ...a, entry: overrides } : a)));
          setEditing(null);
        }}
      />
      {canEdit ? (
        <SearchableSelect
          value=""
          onChange={(key) => {
            if (key) add(key);
          }}
          fetchOptions={fetchOptions}
          paginated
          pageSize={PRODUCT_PAGE_SIZE}
          placeholder="Add accessory or product"
          aria-label={`Add accessory or product${label ? ` to ${label}` : ''}`}
          emptyMessage="No accessories or products found."
          clearable={false}
          createOption={{
            label: (query) => (query.trim() ? `Create accessory "${query.trim()}"` : null),
            onCreate: (query) => void onCreate(query.trim()),
          }}
        />
      ) : null}
    </div>
  );
}

export default AccessoryListField;

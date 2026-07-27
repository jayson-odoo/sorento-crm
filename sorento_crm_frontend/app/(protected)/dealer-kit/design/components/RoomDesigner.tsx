'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Box as BoxIcon, Check, Plus, RotateCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  clampBoxIntoRoom,
  areaSquareMetres,
  boxesOverlap,
  type Point,
} from '@/lib/dealer-kit/roomGeometry';
import { listPickerProducts } from '../../services/productPickerService';
import {
  createSelection,
  getSelection,
  saveRoom,
  setSelectionLine,
  type Room,
  type Selection,
  type SelectionLine,
} from '../../services/selectionService';
import {
  boxesForSelection,
  placementsOf,
  quantityOf,
  removeBox,
  type PlacedBox,
} from '@/lib/dealer-kit/roomBoxes';
import { RoomPlan } from './RoomPlan';
import { RoomScene } from './RoomScene';

/**
 * The room designer: pick products, shape the room, place them, confirm.
 *
 * Plan and 3D are two views of ONE state, not two editors. Dragging in the plan
 * moves the box in 3D because there is only one array of boxes - the moment
 * they become separate models they start disagreeing, and the user is the one
 * who finds out.
 *
 * **The Selection is the source of truth for WHAT, the room for WHERE.** Which
 * products and how many lives on the server and comes back priced for whoever
 * is looking; the outline and the placements are saved alongside it. Nothing
 * price-shaped is computed here - a designer that did its own arithmetic would
 * be a second price list nobody knew they were maintaining.
 *
 * Sizes come from the Selection too, so a box is at the product's real
 * dimensions when the catalogue has them and an obvious placeholder when it
 * does not (AC-V1, AC-V2).
 */

/** A 4m x 3m room to start from. Reshaping four corners beats drawing from nothing. */
const STARTING_ROOM: Point[] = [
  { x: 0, y: 0 },
  { x: 4000, y: 0 },
  { x: 4000, y: 3000 },
  { x: 0, y: 3000 },
];

/** Where this design is remembered between visits, so a reload is not a restart. */
const LAST_SELECTION_KEY = 'dealer-kit:last-selection';

export function RoomDesigner() {
  const queryClient = useQueryClient();
  const [selectionId, setSelectionId] = useState<string | null>(null);
  const [outline, setOutline] = useState<Point[]>(STARTING_ROOM);
  const [placed, setPlaced] = useState<PlacedBox[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [productToAdd, setProductToAdd] = useState('');
  const [dirty, setDirty] = useState(false);
  const hydrated = useRef(false);

  useEffect(() => {
    setSelectionId(window.localStorage.getItem(LAST_SELECTION_KEY));
  }, []);

  const { data: products = [], isLoading: productsLoading } = useQuery({
    queryKey: ['dealer-kit', 'picker-products'],
    queryFn: listPickerProducts,
  });

  const {
    data: selection,
    isLoading: selectionLoading,
    isError: selectionMissing,
  } = useQuery({
    queryKey: ['dealer-kit', 'selection', selectionId],
    queryFn: () => getSelection(selectionId!),
    enabled: !!selectionId,
    retry: false,
  });

  /**
   * Forget a remembered design the server will not give us.
   *
   * The last design is remembered in this browser so a reload is not a restart,
   * but the row can disappear underneath it - deleted, or belonging to a
   * company the user has since switched away from. Left alone, every read 404s,
   * every add fails against the stale id, and the designer is bricked until
   * somebody clears their browser storage. Forgetting it starts a fresh one on
   * the next action, which is what the user wanted anyway.
   */
  useEffect(() => {
    if (!selectionMissing || !selectionId) return;
    window.localStorage.removeItem(LAST_SELECTION_KEY);
    setSelectionId(null);
    hydrated.current = false;
    setPlaced([]);
  }, [selectionMissing, selectionId]);

  // The server owns which products and their sizes; local state owns where they
  // stand. Rebuilding on every selection change keeps the two in step without a
  // second copy of the line list.
  useEffect(() => {
    if (!selection) return;
    setPlaced((current) => boxesForSelection(selection, current));
    if (!hydrated.current && selection.room?.outline?.length) {
      setOutline(selection.room.outline);
      hydrated.current = true;
    }
  }, [selection]);

  const ensureSelection = useCallback(async (): Promise<string> => {
    if (selectionId) return selectionId;
    const created = await createSelection();
    window.localStorage.setItem(LAST_SELECTION_KEY, created.id);
    setSelectionId(created.id);
    queryClient.setQueryData(['dealer-kit', 'selection', created.id], created);
    return created.id;
  }, [selectionId, queryClient]);

  const lineMutation = useMutation({
    mutationFn: async ({ productId, quantity }: { productId: string; quantity: number }) => {
      const id = await ensureSelection();
      return setSelectionLine(id, productId, quantity);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(['dealer-kit', 'selection', updated.id], updated);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const roomMutation = useMutation({
    mutationFn: async (room: Room) => {
      const id = await ensureSelection();
      return saveRoom(id, room);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(['dealer-kit', 'selection', updated.id], updated);
      setDirty(false);
      toast.success('Design saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const addProduct = useCallback(() => {
    const product = products.find((candidate) => candidate.id === productToAdd);
    if (!product) return;

    const line = selection?.lines.find((row) => row.productId === product.id);
    lineMutation.mutate({ productId: product.id, quantity: (line?.quantity ?? 0) + 1 });
    setProductToAdd('');
  }, [productToAdd, products, selection, lineMutation]);

  const moveBox = useCallback(
    (boxId: string, x: number, y: number) => {
      setDirty(true);
      setPlaced((current) =>
        current.map((box) => {
          if (box.id !== boxId) return box;
          // Tidy rather than refuse: a drop half through a wall is a clear
          // intent the system can simply fix (AC-V4).
          return clampBoxIntoRoom({ ...box, x, y }, outline) as PlacedBox;
        }),
      );
    },
    [outline],
  );

  const changeOutline = useCallback((next: Point[]) => {
    setOutline(next);
    setDirty(true);
  }, []);

  const rotateSelected = useCallback(() => {
    setDirty(true);
    setPlaced((current) =>
      current.map((box) =>
        box.id === selectedId ? { ...box, rotation: (box.rotation + 90) % 360 } : box,
      ),
    );
  }, [selectedId]);

  const removeSelected = useCallback(() => {
    const box = placed.find((candidate) => candidate.id === selectedId);
    if (!box) return;

    // Take the clicked copy out locally FIRST, renumbering what is left, then
    // tell the server the new count. Sending only "one fewer" would leave the
    // rebuild deleting the last copy instead of the one they clicked.
    const remaining = removeBox(placed, box.id);
    setPlaced(remaining);
    setSelectedId(null);
    setDirty(true);
    lineMutation.mutate({
      productId: box.productId,
      quantity: quantityOf(remaining, box.productId),
    });
  }, [placed, selectedId, lineMutation]);

  /**
   * Put the canvas back to an empty room.
   *
   * The designer reopens the last design so a reload is not a restart, which
   * means without this there is no way to start a second one - the first design
   * would follow the user forever. The old design is NOT deleted: it is saved
   * work, and forgetting it here is not the same as throwing it away.
   */
  const startFresh = useCallback(() => {
    window.localStorage.removeItem(LAST_SELECTION_KEY);
    hydrated.current = false;
    setSelectionId(null);
    setPlaced([]);
    setOutline(STARTING_ROOM);
    setSelectedId(null);
    setDirty(false);
  }, []);

  const save = useCallback(() => {
    roomMutation.mutate({
      outline,
      placements: placementsOf(placed),
    });
  }, [outline, placed, roomMutation]);

  const collisions = useMemo(() => {
    const clashing = new Set<string>();
    for (let i = 0; i < placed.length; i += 1) {
      for (let j = i + 1; j < placed.length; j += 1) {
        if (boxesOverlap(placed[i], placed[j])) {
          clashing.add(placed[i].id);
          clashing.add(placed[j].id);
        }
      }
    }
    return clashing;
  }, [placed]);

  const area = areaSquareMetres(outline);
  const estimated = placed.filter((box) => box.isEstimated);
  const estimatedNames = Array.from(new Set(estimated.map((box) => box.code)));
  const lines = selection?.lines ?? [];
  const busy = lineMutation.isPending || roomMutation.isPending;

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <div className="min-w-0 flex-1">
        <Card>
          <CardHeader className="flex flex-col gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="text-sm">The room</CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              {dirty && (
                <span className="text-xs text-muted-foreground">Unsaved changes</span>
              )}
              <Button size="sm" variant="outline" onClick={startFresh} disabled={busy}>
                <Plus className="size-4" />
                New design
              </Button>
              <Button size="sm" variant={dirty ? 'primary' : 'outline'} onClick={save} disabled={busy}>
                <Check className="size-4" />
                {busy ? 'Saving' : 'Save design'}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="plan">
              <TabsList>
                <TabsTrigger value="plan">Plan</TabsTrigger>
                <TabsTrigger value="3d">3D</TabsTrigger>
              </TabsList>

              <TabsContent value="plan" className="pt-3">
                <RoomPlan
                  outline={outline}
                  boxes={placed}
                  selectedBoxId={selectedId}
                  onOutlineChange={changeOutline}
                  onMoveBox={moveBox}
                  onSelectBox={setSelectedId}
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  Drag a corner to reshape the room, or drag a product to move it. Everything
                  snaps to 50mm.
                </p>
              </TabsContent>

              <TabsContent value="3d" className="pt-3">
                <RoomScene
                  outline={outline}
                  boxes={placed}
                  selectedBoxId={selectedId}
                  onSelectBox={setSelectedId}
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  Drag to orbit, scroll to zoom. Each product is a box at its real size.
                </p>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>

      <aside className="w-full shrink-0 lg:w-80">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Products in this room</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 pb-4">
            <div className="flex gap-2">
              <div className="min-w-0 flex-1">
                <SearchableSelect
                  id="dk-design-add-product"
                  value={productToAdd}
                  onChange={setProductToAdd}
                  options={products.map((product) => ({
                    value: product.id,
                    label: `${product.code} · ${product.name}`,
                  }))}
                  placeholder={productsLoading ? 'Loading products' : 'Add a product'}
                />
              </div>
              <Button
                size="sm"
                aria-label="Add product to room"
                disabled={!productToAdd || busy}
                onClick={addProduct}
              >
                <Plus className="size-4" />
              </Button>
            </div>

            {selectionLoading && <Skeleton className="h-16 w-full" />}

            {!selectionLoading && lines.length === 0 && (
              <div className="rounded-lg border border-dashed border-border p-4 text-center">
                <BoxIcon className="mx-auto size-5 text-muted-foreground" />
                <p className="mt-2 text-xs font-medium text-foreground">Nothing placed yet</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Add a product and it appears in the room at its real size.
                </p>
              </div>
            )}

            {lines.map((line) => (
              <SelectionRow
                key={line.lineId}
                line={line}
                selected={placed.some(
                  (box) => box.productId === line.productId && box.id === selectedId,
                )}
                clashing={placed.some(
                  (box) => box.productId === line.productId && collisions.has(box.id),
                )}
                onSelect={() => {
                  const box = placed.find((candidate) => candidate.productId === line.productId);
                  if (box) setSelectedId(box.id);
                }}
              />
            ))}

            {selectedId && (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={rotateSelected}>
                  <RotateCw className="size-4" />
                  Rotate
                </Button>
                <Button variant="outline" size="sm" onClick={removeSelected} disabled={busy}>
                  <Trash2 className="size-4 text-destructive" />
                  Remove
                </Button>
              </div>
            )}

            {estimatedNames.length > 0 && (
              <Alert>
                <AlertTriangle className="size-4" />
                <AlertTitle className="text-xs">Sizes are estimated</AlertTitle>
                <AlertDescription className="text-xs">
                  {/* Naming them matters: "one product" leaves the user hunting
                      for which box is the lie (AC-V2). */}
                  {estimatedNames.join(', ')} {estimatedNames.length === 1 ? 'is' : 'are'} drawn
                  at a default size because the catalogue has no dimensions.
                </AlertDescription>
              </Alert>
            )}

            {selection && selection.unavailableCount > 0 && (
              <Alert variant="destructive">
                <AlertTriangle className="size-4" />
                <AlertTitle className="text-xs">
                  {selection.unavailableCount} product
                  {selection.unavailableCount === 1 ? '' : 's'} cannot be ordered
                </AlertTitle>
                <AlertDescription className="text-xs">
                  They stay in the design so you can see what changed, and they are left out of
                  the total.
                </AlertDescription>
              </Alert>
            )}

            <div className="mt-2 space-y-1 border-t border-border pt-2 text-xs text-muted-foreground">
              <div className="flex justify-between">
                <span>Room area</span>
                <span>{area.toFixed(1)} m²</span>
              </div>
              <div className="flex justify-between">
                <span>Products</span>
                <span>{placed.length}</span>
              </div>
              {selection?.total && (
                <div className="flex justify-between pt-1 text-sm font-medium text-foreground">
                  <span>Total</span>
                  <span>
                    {selection.currency} {selection.total}
                  </span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function SelectionRow({
  line,
  selected,
  clashing,
  onSelect,
}: {
  line: SelectionLine;
  selected: boolean;
  clashing: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-label={`Select ${line.productCode ?? line.productName}`}
      className={`flex items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-start ${
        selected ? 'border-primary bg-primary/5' : 'border-border'
      }`}
    >
      <span className="min-w-0">
        <span className="block truncate font-mono text-xs">
          {line.productCode ?? line.productName}
          {line.quantity > 1 && <span className="text-muted-foreground"> ×{line.quantity}</span>}
        </span>
        <span className="block text-[10px] text-muted-foreground">
          {line.dimensionsMm
            ? `${line.dimensionsMm.length} x ${line.dimensionsMm.width} x ${line.dimensionsMm.height} mm`
            : 'No dimensions in the catalogue'}
          {line.lineTotal ? ` · ${line.lineTotal}` : ''}
        </span>
      </span>
      <span className="flex shrink-0 gap-1">
        {!line.isAvailable && (
          <Badge variant="destructive" appearance="ghost" className="text-[9px]">
            {line.unavailableReason === 'discontinued' ? 'Discontinued' : 'Unavailable'}
          </Badge>
        )}
        {clashing && (
          <Badge variant="warning" appearance="ghost" className="text-[9px]">
            Overlapping
          </Badge>
        )}
      </span>
    </button>
  );
}

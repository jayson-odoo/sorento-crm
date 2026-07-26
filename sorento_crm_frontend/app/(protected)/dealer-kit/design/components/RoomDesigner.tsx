'use client';

import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Box as BoxIcon, Plus, RotateCw, Trash2 } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  clampBoxIntoRoom,
  areaSquareMetres,
  boxesOverlap,
  type Point,
} from '@/lib/dealer-kit/roomGeometry';
import { listPickerProducts } from '../../services/productPickerService';
import { RoomPlan } from './RoomPlan';
import { RoomScene, UNKNOWN_SIZE_MM, type SceneBox } from './RoomScene';

/**
 * The room designer: pick products, shape the room, place them, confirm.
 *
 * Plan and 3D are two views of ONE state, not two editors. Dragging in the plan
 * moves the box in 3D because there is only one array of boxes - the moment
 * they become separate models they start disagreeing, and the user is the one
 * who finds out.
 *
 * Phase 1: rooms start as a rectangle the user reshapes, products come from the
 * real catalogue, and nothing is persisted yet. Selection and the quote handoff
 * are the next phase; the shapes here are what they will be held to.
 */

/** A 4m x 3m room to start from. Reshaping four corners beats drawing from nothing. */
const STARTING_ROOM: Point[] = [
  { x: 0, y: 0 },
  { x: 4000, y: 0 },
  { x: 4000, y: 3000 },
  { x: 0, y: 3000 },
];

interface PlacedProduct extends SceneBox {
  productId: string;
  code: string;
}

export function RoomDesigner() {
  const [outline, setOutline] = useState<Point[]>(STARTING_ROOM);
  const [placed, setPlaced] = useState<PlacedProduct[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [productToAdd, setProductToAdd] = useState('');

  const { data: products = [], isLoading } = useQuery({
    queryKey: ['dealer-kit', 'picker-products'],
    queryFn: listPickerProducts,
  });

  const addProduct = useCallback(() => {
    const product = products.find((candidate) => candidate.id === productToAdd);
    if (!product) return;

    // Phase 1 has no dimensions on the select payload, so every box is
    // currently an estimate and says so. Wiring real dimensions is a
    // one-field change to the endpoint, not a redesign.
    const size = UNKNOWN_SIZE_MM;

    setPlaced((current) => {
      const id = `placed-${current.length + 1}-${product.id.slice(0, 6)}`;
      // Drop new items in a row rather than on top of each other.
      const nextX = 200 + (current.length % 4) * (size.width + 200);
      const nextY = 200 + Math.floor(current.length / 4) * (size.depth + 200);

      const box: PlacedProduct = {
        id,
        productId: product.id,
        code: product.code,
        label: product.code,
        x: nextX,
        y: nextY,
        width: size.width,
        depth: size.depth,
        heightMm: size.height,
        rotation: 0,
        isEstimated: true,
      };
      return [...current, clampBoxIntoRoom(box, outline) as PlacedProduct];
    });
    setProductToAdd('');
  }, [productToAdd, products, outline]);

  const moveBox = useCallback(
    (boxId: string, x: number, y: number) => {
      setPlaced((current) =>
        current.map((box) => {
          if (box.id !== boxId) return box;
          // Tidy rather than refuse: a drop half through a wall is a clear
          // intent the system can simply fix (AC-V4).
          return clampBoxIntoRoom({ ...box, x, y }, outline) as PlacedProduct;
        }),
      );
    },
    [outline],
  );

  const rotateSelected = useCallback(() => {
    setPlaced((current) =>
      current.map((box) =>
        box.id === selectedId ? { ...box, rotation: (box.rotation + 90) % 360 } : box,
      ),
    );
  }, [selectedId]);

  const removeSelected = useCallback(() => {
    setPlaced((current) => current.filter((box) => box.id !== selectedId));
    setSelectedId(null);
  }, [selectedId]);

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
  const estimated = placed.filter((box) => box.isEstimated).length;

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <div className="min-w-0 flex-1">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">The room</CardTitle>
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
                  onOutlineChange={setOutline}
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
                  placeholder={isLoading ? 'Loading products' : 'Add a product'}
                />
              </div>
              <Button
                size="sm"
                aria-label="Add product to room"
                disabled={!productToAdd}
                onClick={addProduct}
              >
                <Plus className="size-4" />
              </Button>
            </div>

            {placed.length === 0 && (
              <div className="rounded-lg border border-dashed border-border p-4 text-center">
                <BoxIcon className="mx-auto size-5 text-muted-foreground" />
                <p className="mt-2 text-xs font-medium text-foreground">Nothing placed yet</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Add a product and it appears in the room at its real size.
                </p>
              </div>
            )}

            {placed.map((box) => (
              <button
                key={box.id}
                type="button"
                onClick={() => setSelectedId(box.id)}
                aria-label={`Select ${box.code}`}
                className={`flex items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-start ${
                  box.id === selectedId ? 'border-primary bg-primary/5' : 'border-border'
                }`}
              >
                <span className="min-w-0">
                  <span className="block truncate font-mono text-xs">{box.code}</span>
                  <span className="block text-[10px] text-muted-foreground">
                    {box.width} x {box.depth} x {box.heightMm} mm
                  </span>
                </span>
                {collisions.has(box.id) && (
                  <Badge variant="warning" appearance="ghost" className="shrink-0 text-[9px]">
                    Overlapping
                  </Badge>
                )}
              </button>
            ))}

            {selectedId && (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={rotateSelected}>
                  <RotateCw className="size-4" />
                  Rotate
                </Button>
                <Button variant="outline" size="sm" onClick={removeSelected}>
                  <Trash2 className="size-4 text-destructive" />
                  Remove
                </Button>
              </div>
            )}

            {estimated > 0 && (
              <Alert>
                <AlertTriangle className="size-4" />
                <AlertTitle className="text-xs">Sizes are estimated</AlertTitle>
                <AlertDescription className="text-xs">
                  {estimated} product{estimated === 1 ? '' : 's'} rendered at a default size
                  because the catalogue has no dimensions for {estimated === 1 ? 'it' : 'them'}.
                  A wrong-sized box that looks right is worse than one that says so.
                </AlertDescription>
              </Alert>
            )}

            <div className="mt-2 border-t border-border pt-2 text-xs text-muted-foreground">
              <div className="flex justify-between">
                <span>Room area</span>
                <span>{area.toFixed(1)} m²</span>
              </div>
              <div className="flex justify-between">
                <span>Products</span>
                <span>{placed.length}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

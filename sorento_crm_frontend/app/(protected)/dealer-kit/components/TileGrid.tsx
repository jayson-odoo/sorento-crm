'use client';

import { createContext, useContext } from 'react';
import { Check, ImageOff, Package } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ResolvedTile, TileField } from '@/lib/dealer-kit/types';

/**
 * A resolved collection, rendered as tiles.
 *
 * Shared by the editor canvas and the public renderer, for the same reason
 * `BlockPreview` is: a second tile renderer would drift from this one, and the
 * drift would only be visible in the PDF, which is the worst place to find it.
 *
 * Density is the BLOCK's own property, not the grid's. That is what lets layout
 * derivation stack a collection block full-width on mobile without turning a
 * 4-across product grid into a 4-across grid on a phone.
 *
 * A tile shows a price only when the server sent one. `null` means this viewer
 * may not see it, and there is no number in the payload to reveal (AC-G7) - so
 * there is deliberately no "hide it with CSS" path here.
 */

const GAP = 'gap-3';

/**
 * Ticking products in a published catalogue.
 *
 * A context rather than a prop chain because the tiles sit at the bottom of
 * section -> block -> grid, and threading a callback through every renderer
 * would put "is this catalogue shoppable" into three components that have no
 * other reason to know.
 *
 * Absent by default: the editor canvas and the PDF render exactly as before.
 */
export interface CataloguePicking {
  picked: string[];
  onToggle: (productId: string) => void;
}

const PickingContext = createContext<CataloguePicking | null>(null);

export const CataloguePickingProvider = PickingContext.Provider;

export function useCataloguePicking(): CataloguePicking | null {
  return useContext(PickingContext);
}

function fieldSet(fields: TileField[]): Set<TileField> {
  return new Set(fields);
}

function TileImage({ tile, show }: { tile: ResolvedTile; show: boolean }) {
  if (!show) return null;

  return (
    <div className="flex aspect-square w-full items-center justify-center overflow-hidden rounded border border-border bg-muted/40">
      {tile.imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- product images are
        // remote CDN objects of unknown dimensions; next/image adds no value here
        // and its loader would need a per-tenant domain allowlist.
        <img
          src={tile.imageUrl}
          alt={tile.productName}
          className="size-full object-cover"
          loading="lazy"
        />
      ) : (
        <ImageOff className="size-5 text-muted-foreground" aria-hidden />
      )}
    </div>
  );
}

export function ProductTile({
  tile,
  fields,
}: {
  tile: ResolvedTile;
  fields: TileField[];
}) {
  const show = fieldSet(fields);
  const picking = useCataloguePicking();
  const picked = picking?.picked.includes(tile.productId) ?? false;

  return (
    <article
      className={cn(
        'relative flex min-w-0 flex-col gap-1.5 rounded-lg border bg-background p-2',
        picking ? 'cursor-pointer transition-colors hover:border-primary' : '',
        picked ? 'border-primary ring-1 ring-primary' : 'border-border',
      )}
      data-dk-tile={tile.productId}
      data-dk-tile-picked={picked ? 'true' : undefined}
      // The whole tile is the target, not a small checkbox: on a phone in a
      // showroom, a 16px box is a miss.
      onClick={picking ? () => picking.onToggle(tile.productId) : undefined}
      role={picking ? 'button' : undefined}
      aria-pressed={picking ? picked : undefined}
    >
      {picking && (
        <span
          className={cn(
            'absolute end-1 top-1 z-10 flex size-5 items-center justify-center rounded-full border',
            picked
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border bg-background/90 text-transparent',
          )}
          aria-hidden
        >
          <Check className="size-3" />
        </span>
      )}
      <TileImage tile={tile} show={show.has('image')} />

      {show.has('name') && (
        <p className="truncate text-xs font-medium text-foreground" title={tile.productName}>
          {tile.productName}
        </p>
      )}

      {show.has('code') && (
        <p className="truncate font-mono text-[10px] text-muted-foreground">{tile.productCode}</p>
      )}

      {show.has('dimensions') && tile.dimensions && (
        <p className="truncate text-[10px] text-muted-foreground">{tile.dimensions}</p>
      )}

      {show.has('badges') && tile.badges.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tile.badges.map((badge) => (
            // A badge is artwork and a claim, never a link to the certificate
            // itself - that document has its own access gating (AC-E6).
            <Badge key={badge} variant="outline" appearance="ghost" className="text-[9px]">
              {badge}
            </Badge>
          ))}
        </div>
      )}

      {show.has('price') && tile.price && (
        <p className="mt-auto text-xs font-semibold text-foreground">{tile.price}</p>
      )}

      {show.has('price') && tile.invoicePrice && (
        <p className="text-[10px] text-muted-foreground">Invoice {tile.invoicePrice}</p>
      )}
    </article>
  );
}

export function TileGrid({
  tiles,
  fields,
  columns,
  className,
}: {
  tiles: ResolvedTile[];
  fields: TileField[];
  /** Tiles across at the CURRENTLY rendered breakpoint. */
  columns: number;
  className?: string;
}) {
  if (tiles.length === 0) {
    return (
      <div className="flex h-full min-h-20 flex-col items-center justify-center gap-1 rounded border border-dashed border-border p-3 text-center">
        <Package className="size-4 text-muted-foreground" aria-hidden />
        <p className="text-[11px] font-medium text-foreground">No products to show</p>
        <p className="text-[10px] text-muted-foreground">
          Every product in this collection is hidden from this viewer, or the collection is
          empty.
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn('grid', GAP, className)}
      // Column count is data from the document, so it cannot be a Tailwind class
      // generated ahead of time.
      style={{ gridTemplateColumns: `repeat(${Math.max(1, columns)}, minmax(0, 1fr))` }}
      data-dk-tile-grid
    >
      {tiles.map((tile) => (
        <ProductTile key={tile.productId} tile={tile} fields={fields} />
      ))}
    </div>
  );
}

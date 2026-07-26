'use client';

import { Image as ImageIcon, LayoutGrid, Package, Square } from 'lucide-react';

import { cn } from '@/lib/utils';
import type {
  Block,
  ResolvedBundle,
  ResolvedTile,
  TileField,
} from '@/lib/dealer-kit/types';
import type { Breakpoint } from '@/lib/dealer-kit/deriveLayout';
import { BundleCard } from './BundleCard';
import { TileGrid } from './TileGrid';

/**
 * How a block renders. Shared by the editor canvas and the public renderer, so
 * what a Designer arranges is literally what a reader sees - the alternative is
 * two renderers that drift, which is the same trap the PDF path avoids by
 * printing this same tree through Chromium.
 *
 * Bindings resolve at READ time. A collection block shows its binding here
 * because Phase 1 has no resolver; it never shows a price, because a price in a
 * document is a defect (AC-G1).
 */

const TEXT_SCALE: Record<string, string> = {
  sm: 'text-xs',
  base: 'text-sm',
  lg: 'text-base',
  xl: 'text-lg',
  '2xl': 'text-2xl',
};

function BindingPlaceholder({
  icon: Icon,
  label,
  detail,
  bound,
}: {
  icon: typeof LayoutGrid;
  label: string;
  detail: string;
  bound: boolean;
}) {
  return (
    <div
      className={cn(
        'flex h-full min-h-16 w-full flex-col items-center justify-center gap-1 rounded border border-dashed p-2 text-center',
        bound ? 'border-border bg-muted/40' : 'border-amber-500/60 bg-amber-500/5',
      )}
    >
      <Icon className={cn('size-4', bound ? 'text-muted-foreground' : 'text-amber-600')} />
      <span className="text-[11px] font-medium text-foreground">{label}</span>
      <span className="line-clamp-2 text-[10px] text-muted-foreground">{detail}</span>
    </div>
  );
}

/**
 * What a block's resolved bindings look like when they are available.
 *
 * Optional on purpose: the editor canvas resolves against a Designer's own
 * viewer context, the public renderer resolves against the reader's, and a bare
 * preview (a test, a thumbnail) passes nothing and gets placeholders. One
 * component covers all three rather than three that drift.
 */
export interface ResolvedBinding {
  tiles?: ResolvedTile[];
  tileFields?: TileField[];
  bundle?: ResolvedBundle;
}

export function BlockPreview({
  block,
  resolved,
  breakpoint,
}: {
  block: Block;
  resolved?: ResolvedBinding;
  breakpoint?: Breakpoint;
}) {
  const { props } = block;

  switch (props.kind) {
    case 'heading':
      return (
        <p
          className={cn(
            'font-semibold leading-tight text-foreground',
            TEXT_SCALE[props.scale ?? '2xl'],
            props.align === 'center' && 'text-center',
            props.align === 'right' && 'text-right',
          )}
        >
          {props.text || 'Untitled heading'}
        </p>
      );

    case 'text':
      return (
        <p
          className={cn(
            'leading-relaxed text-muted-foreground',
            TEXT_SCALE[props.scale ?? 'base'],
            props.align === 'center' && 'text-center',
            props.align === 'right' && 'text-right',
          )}
        >
          {props.text || 'Empty text block'}
        </p>
      );

    case 'image':
    case 'asset': {
      // An asset id resolves to a URL through the asset library, which is a
      // later slice. Until it exists this renders as UNRESOLVED rather than
      // reaching for a placeholder image - a stand-in picture would look like a
      // working binding and hide the fact that nothing is wired yet.
      return (
        <BindingPlaceholder
          icon={ImageIcon}
          label={props.assetId ? 'Image' : 'No image chosen'}
          detail={props.assetId ? 'Resolved from the asset library' : 'Pick one from the asset library'}
          bound={Boolean(props.assetId)}
        />
      );
    }

    case 'collection': {
      // A resolved binding renders for real, INCLUDING when it resolved to
      // nothing. "Chosen but everything filtered out" and "nothing chosen" are
      // different situations and a Designer needs to be able to tell them
      // apart - telling someone who just picked a discontinued product that
      // they chose nothing sends them hunting for the wrong problem. Only an
      // absent binding falls through to the placeholder.
      if (resolved?.tiles !== undefined) {
        return (
          <TileGrid
            tiles={resolved.tiles}
            fields={resolved.tileFields ?? ['image', 'name', 'code', 'price']}
            columns={props.columns[breakpoint ?? 'desktop']}
          />
        );
      }

      return (
        <BindingPlaceholder
          icon={LayoutGrid}
          label={props.collectionId ? 'Product collection' : 'No products chosen'}
          detail={
            props.collectionId
              ? `${props.columns.desktop} across on desktop`
              : 'Choose the products this block shows'
          }
          bound={Boolean(props.collectionId && props.tileTemplateId)}
        />
      );
    }

    case 'bundle': {
      if (resolved?.bundle) return <BundleCard bundle={resolved.bundle} />;

      return (
        <BindingPlaceholder
          icon={Package}
          label={props.bundleId ? 'Bundle' : 'No bundle bound'}
          detail={
            props.bundleId
              ? 'Renders as one priced heading with its components beneath'
              : 'Choose which bundle this block shows'
          }
          bound={Boolean(props.bundleId)}
        />
      );
    }

    case 'artboard':
      return (
        <BindingPlaceholder
          icon={Square}
          label="Artboard"
          detail={`${props.children.length} free-positioned items`}
          bound
        />
      );

    case 'spacer':
      return <div className="h-full w-full rounded bg-muted/30" aria-hidden />;

    default:
      return null;
  }
}

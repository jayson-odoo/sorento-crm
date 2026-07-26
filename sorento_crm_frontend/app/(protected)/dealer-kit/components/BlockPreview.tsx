'use client';

import { Image as ImageIcon, LayoutGrid, Package, Square } from 'lucide-react';

import { cn } from '@/lib/utils';
import { MOCK_ASSETS, MOCK_TILE_TEMPLATES } from '../__mocks__/fixtures';
import type { Block } from '@/lib/dealer-kit/types';

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

export function BlockPreview({ block }: { block: Block }) {
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
      const asset = MOCK_ASSETS.find((candidate) => candidate.id === props.assetId);

      if (!asset) {
        return (
          <BindingPlaceholder
            icon={ImageIcon}
            label="No image chosen"
            detail="Pick one from the asset library"
            bound={false}
          />
        );
      }

      return (
        // eslint-disable-next-line @next/next/no-img-element -- fixture URL in the Phase 1 prototype
        <img
          src={asset.url}
          alt={props.alt || asset.name}
          className={cn(
            'h-full w-full rounded',
            props.fit === 'contain' ? 'object-contain' : 'object-cover',
          )}
        />
      );
    }

    case 'collection': {
      const template = MOCK_TILE_TEMPLATES.find(
        (candidate) => candidate.id === props.tileTemplateId,
      );

      return (
        <BindingPlaceholder
          icon={LayoutGrid}
          label={props.collectionId ? 'Product collection' : 'No collection bound'}
          detail={
            props.collectionId
              ? `${template?.name ?? 'No tile design'} · ${props.columns.desktop} across`
              : 'Choose the products this block shows'
          }
          bound={Boolean(props.collectionId && props.tileTemplateId)}
        />
      );
    }

    case 'bundle':
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

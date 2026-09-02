'use client';

/**
 * Top toolbar for the tag canvas editor.
 *
 * Tools, add-layer buttons, undo/redo, zoom, selection actions. The preview
 * eye used to live here as one whole-tag chip (D41); it moved onto each
 * previewable block itself (D10, S6) - hover/select a block on the canvas for
 * its own eye, so there is nothing left for the toolbar to show.
 */

import {
  Banknote,
  Barcode,
  Boxes,
  Copy,
  Expand,
  Group,
  Hand,
  MousePointer2,
  Package,
  Shuffle,
  Sparkles,
  ImageIcon,
  Minus,
  Plus,
  Redo2,
  RectangleHorizontal,
  Shapes,
  Tag,
  Trash2,
  Type,
  Undo2,
  Ungroup,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

/** Which pointer tool is active (D35). */
export type CanvasTool = 'select' | 'hand';

interface CanvasToolbarProps {
  tool: CanvasTool;
  onToolChange: (tool: CanvasTool) => void;
  onAddText: () => void;
  onAddShape: () => void;
  onAddImage: () => void;
  onAddProductSlot: () => void;
  onAddPriceBadge: () => void;
  onAddBadge: () => void;
  onAddBarcode: () => void;
  onAddProduct: () => void;
  onAddSet: () => void;
  onAddAlternativesRow: () => void;
  onAddAccessoriesStrip: () => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomReset: () => void;
  onFit: () => void;
  onDeleteSelected: () => void;
  onDuplicateSelected: () => void;
  onGroupSelected: () => void;
  onUngroupSelected: () => void;
  hasSelection: boolean;
  hasMultiSelection: boolean;
  selectionIsGroup: boolean;
}

function ToolbarButton({
  icon: Icon,
  label,
  onClick,
  disabled,
  shortcut,
  active,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  shortcut?: string;
  active?: boolean;
}) {
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={cn('h-8 w-8 p-0', active && 'bg-accent text-accent-foreground')}
            onClick={onClick}
            disabled={disabled}
            aria-pressed={active}
          >
            <Icon className="size-4" />
            <span className="sr-only">{label}</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">
          {label}
          {shortcut && <span className="ml-2 text-muted-foreground">{shortcut}</span>}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function CanvasToolbar({
  tool,
  onToolChange,
  onAddText,
  onAddShape,
  onAddImage,
  onAddProductSlot,
  onAddPriceBadge,
  onAddBadge,
  onAddBarcode,
  onAddProduct,
  onAddSet,
  onAddAlternativesRow,
  onAddAccessoriesStrip,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  zoom,
  onZoomIn,
  onZoomOut,
  onZoomReset,
  onFit,
  onDeleteSelected,
  onDuplicateSelected,
  onGroupSelected,
  onUngroupSelected,
  hasSelection,
  hasMultiSelection,
  selectionIsGroup,
}: CanvasToolbarProps) {
  return (
    <div className="flex h-10 shrink-0 items-center gap-1 border-b bg-background px-2">
      {/* Tools */}
      <ToolbarButton
        icon={MousePointer2}
        label="Select"
        onClick={() => onToolChange('select')}
        active={tool === 'select'}
        shortcut="V"
      />
      <ToolbarButton
        icon={Hand}
        label="Hand"
        onClick={() => onToolChange('hand')}
        active={tool === 'hand'}
        shortcut="H"
      />

      <Separator orientation="vertical" className="mx-1 h-5" />

      {/* Add layer buttons */}
      <ToolbarButton icon={Type} label="Add Text" onClick={onAddText} />
      <ToolbarButton icon={Shapes} label="Add Shape" onClick={onAddShape} />
      <ToolbarButton icon={ImageIcon} label="Add Image" onClick={onAddImage} />
      <ToolbarButton
        icon={RectangleHorizontal}
        label="Add Product Slot"
        onClick={onAddProductSlot}
      />
      <ToolbarButton
        icon={Banknote}
        label="Add Price Badge"
        onClick={onAddPriceBadge}
      />
      <ToolbarButton icon={Tag} label="Add Badge" onClick={onAddBadge} />
      <ToolbarButton icon={Barcode} label="Add Barcode" onClick={onAddBarcode} />

      <Separator orientation="vertical" className="mx-1 h-5" />

      {/* Product-bound blocks and presets */}
      <ToolbarButton icon={Package} label="Add Product" onClick={onAddProduct} />
      <ToolbarButton icon={Boxes} label="Add Set" onClick={onAddSet} />
      <ToolbarButton
        icon={Shuffle}
        label="Add Alternatives Row"
        onClick={onAddAlternativesRow}
      />
      <ToolbarButton
        icon={Sparkles}
        label="Add Accessories Strip"
        onClick={onAddAccessoriesStrip}
      />

      <Separator orientation="vertical" className="mx-1 h-5" />

      {/* Undo / Redo */}
      <ToolbarButton
        icon={Undo2}
        label="Undo"
        onClick={onUndo}
        disabled={!canUndo}
        shortcut="Ctrl+Z"
      />
      <ToolbarButton
        icon={Redo2}
        label="Redo"
        onClick={onRedo}
        disabled={!canRedo}
        shortcut="Ctrl+Shift+Z"
      />

      <Separator orientation="vertical" className="mx-1 h-5" />

      {/* Zoom controls */}
      <ToolbarButton icon={Minus} label="Zoom Out" onClick={onZoomOut} />
      <button
        type="button"
        className="min-w-[48px] rounded px-1 text-center text-xs tabular-nums text-muted-foreground hover:bg-accent"
        onClick={onZoomReset}
        title="Zoom to 100% (Ctrl+1)"
      >
        {Math.round(zoom * 100)}%
      </button>
      <ToolbarButton icon={Plus} label="Zoom In" onClick={onZoomIn} />
      <ToolbarButton icon={Expand} label="Fit to View" onClick={onFit} shortcut="Ctrl+0" />

      <Separator orientation="vertical" className="mx-1 h-5" />

      {/* Selection actions */}
      <ToolbarButton
        icon={Trash2}
        label="Delete"
        onClick={onDeleteSelected}
        disabled={!hasSelection}
        shortcut="Del"
      />
      <ToolbarButton
        icon={Copy}
        label="Duplicate"
        onClick={onDuplicateSelected}
        disabled={!hasSelection}
        shortcut="Ctrl+D"
      />
      <ToolbarButton
        icon={Group}
        label="Group"
        onClick={onGroupSelected}
        disabled={!hasMultiSelection}
        shortcut="Ctrl+G"
      />
      <ToolbarButton
        icon={Ungroup}
        label="Ungroup"
        onClick={onUngroupSelected}
        disabled={!selectionIsGroup}
      />
    </div>
  );
}

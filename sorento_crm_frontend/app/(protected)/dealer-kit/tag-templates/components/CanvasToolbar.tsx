'use client';

/**
 * Top toolbar for the tag canvas editor.
 *
 * Add layer buttons, undo/redo, zoom, delete, duplicate, group/ungroup.
 */

import {
  Banknote,
  Boxes,
  Copy,
  Group,
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
  DollarSign,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface CanvasToolbarProps {
  onAddText: () => void;
  onAddShape: () => void;
  onAddImage: () => void;
  onAddProductSlot: () => void;
  onAddPriceField: () => void;
  onAddPriceBadge: () => void;
  onAddBadge: () => void;
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
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  shortcut?: string;
}) {
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={onClick}
            disabled={disabled}
          >
            <Icon className="size-4" />
            <span className="sr-only">{label}</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">
          {label}
          {shortcut && (
            <span className="ml-2 text-muted-foreground">{shortcut}</span>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function CanvasToolbar({
  onAddText,
  onAddShape,
  onAddImage,
  onAddProductSlot,
  onAddPriceField,
  onAddPriceBadge,
  onAddBadge,
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
        icon={DollarSign}
        label="Add Price Field"
        onClick={onAddPriceField}
      />
      <ToolbarButton
        icon={Banknote}
        label="Add Price Badge"
        onClick={onAddPriceBadge}
      />
      <ToolbarButton icon={Tag} label="Add Badge" onClick={onAddBadge} />

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
      <span className="min-w-[48px] text-center text-xs tabular-nums text-muted-foreground">
        {Math.round(zoom * 100)}%
      </span>
      <ToolbarButton icon={Plus} label="Zoom In" onClick={onZoomIn} />

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

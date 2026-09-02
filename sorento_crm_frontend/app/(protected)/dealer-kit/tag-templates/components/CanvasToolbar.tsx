'use client';

/**
 * Top toolbar for the tag canvas editor.
 *
 * Tools, add-layer buttons, undo/redo, zoom, selection actions, and the preview
 * chip that says which product the canvas is currently drawn against (D41).
 */

import {
  Banknote,
  Boxes,
  Copy,
  Expand,
  Eye,
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
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
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
  /** The whole chip text while anything is previewing, else null (D53). */
  previewLabel: string | null;
  /** False when the template has no block a product could be shown in. */
  canPreview?: boolean;
  onPreview: () => void;
  onClearPreview: () => void;
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
    // 300ms rather than the app-wide 700ms (M2-07): this toolbar is 15 unlabelled
    // icons in a row, so the label IS the affordance and waiting most of a second
    // for it turns a sweep along the row into a stall. A per-instance
    // `delayDuration` on the Root overrides the shared provider without mounting
    // a second one, so the 300ms skip window still groups the sweep.
    <Tooltip delayDuration={300}>
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
  previewLabel,
  canPreview = true,
  onPreview,
  onClearPreview,
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

      {/* Preview chip (D41, D53). Sits right so it reads as state, not as an action. */}
      <div className="ml-auto flex items-center gap-1">
        {previewLabel ? (
          <div className="flex h-7 items-center gap-1 rounded-full border bg-muted/60 pl-2.5 pr-1 text-xs">
            <button
              type="button"
              className="max-w-[220px] truncate hover:underline"
              onClick={onPreview}
              title={previewLabel}
            >
              {previewLabel}
            </button>
            <button
              type="button"
              className="rounded-full p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
              onClick={onClearPreview}
              title="Stop previewing"
            >
              <X className="size-3" />
            </button>
          </div>
        ) : (
          <ToolbarButton
            icon={Eye}
            label="Preview with a product"
            onClick={onPreview}
            disabled={!canPreview}
          />
        )}
      </div>
    </div>
  );
}

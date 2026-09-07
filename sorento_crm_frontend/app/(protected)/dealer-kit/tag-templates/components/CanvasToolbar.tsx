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
  ChevronDown,
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
  MoreHorizontal,
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
import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
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
  /**
   * Right-aligned actions, one more `ToolbarButton` group at the right end
   * (S7, AC-S7-6) - Full screen / the Template dropdown / Save for the
   * request designer, Versions / Save / Full screen for the template page.
   * Absent renders nothing extra, same toolbar as before this round.
   */
  trailing?: ReactNode;
}

/**
 * One icon button, tooltip carrying the label and shortcut - the shape
 * every tool-group button in this toolbar already uses. Exported so the
 * `trailing` slot's own buttons (Full screen, the Template dropdown, Save -
 * S7) read as one more group of these rather than a row of outlined text
 * chips (AC-S7-6).
 */
export function ToolbarButton({
  icon: Icon,
  iconClassName,
  label,
  onClick,
  disabled,
  shortcut,
  active,
}: {
  icon: React.ComponentType<{ className?: string }>;
  /** Extra classes on the icon itself - `animate-spin` while Save is in flight. */
  iconClassName?: string;
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
          className={cn('h-8 w-8 shrink-0 p-0', active && 'bg-accent text-accent-foreground')}
          onClick={onClick}
          disabled={disabled}
          aria-pressed={active}
        >
          <Icon className={cn('size-4', iconClassName)} />
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

/**
 * `ToolbarButton`'s dropdown sibling (S6): the Template menu opens a
 * `DropdownMenu` instead of firing a click straight away, with a small
 * caret added so the trigger still reads as this button, just one that
 * opens a menu - not a different kind of control in the row.
 */
export function ToolbarDropdownButton({
  icon: Icon,
  label,
  disabled,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <DropdownMenu>
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-auto shrink-0 gap-0.5 px-1.5"
              disabled={disabled}
              aria-label={label}
            >
              <Icon className="size-4" />
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">
          {label}
        </TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end">{children}</DropdownMenuContent>
    </DropdownMenu>
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
  trailing,
}: CanvasToolbarProps) {
  return (
    // `relative` is load-bearing, not decoration (r4d): each button's label is
    // an `sr-only` span, which is `position: absolute`, and a static row is not
    // in its containing-block chain - so `overflow-x-auto` never clipped the
    // labels and they grew the document instead. At 375px that left
    // `documentElement.scrollWidth` at 898 and the whole page scrolling
    // sideways while the toolbar itself sat still.
    <div className="relative flex h-10 min-w-0 shrink-0 flex-nowrap items-center gap-1 overflow-x-auto border-b bg-background px-2">
      {/* Tools */}
      <ToolbarButton
        icon={MousePointer2}
        label="Select"
        onClick={() => onToolChange('select')}
        active={tool === 'select'}
        shortcut="V • Arrow 0.25mm, Shift 1mm, Alt 0.1mm"
      />
      <ToolbarButton
        icon={Hand}
        label="Hand"
        onClick={() => onToolChange('hand')}
        active={tool === 'hand'}
        shortcut="H"
      />

      <Separator orientation="vertical" className="mx-1 h-5 shrink-0" />

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

      <Separator orientation="vertical" className="mx-1 h-5 shrink-0" />

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

      <Separator orientation="vertical" className="mx-1 h-5 shrink-0" />

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

      <Separator orientation="vertical" className="mx-1 h-5 shrink-0" />

      {/* Zoom controls */}
      <ToolbarButton icon={Minus} label="Zoom Out" onClick={onZoomOut} />
      <button
        type="button"
        className="min-w-[48px] shrink-0 rounded px-1 text-center text-xs tabular-nums text-muted-foreground hover:bg-accent"
        onClick={onZoomReset}
        title="Zoom to 100% (Ctrl+1)"
      >
        {Math.round(zoom * 100)}%
      </button>
      <ToolbarButton icon={Plus} label="Zoom In" onClick={onZoomIn} />
      <ToolbarButton icon={Expand} label="Fit to View" onClick={onFit} shortcut="Ctrl+0" />

      <Separator orientation="vertical" className="mx-1 h-5 shrink-0" />

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

      {trailing && (
        <>
          {/* `ml-auto` pushes this group to the true right end (AC-S7-6)
              rather than sitting flush after Ungroup - the row scrolls
              (`overflow-x-auto` on the outer div) rather than clipping it
              at 375px, same as every other group here.

              Below `md` this inline copy of `trailing` is hidden and the
              single overflow trigger just after it (also `ml-auto`, so
              whichever of the two is actually in flow still lands at the
              right end) takes over instead - collapsing three-plus icon
              buttons into one at a width this toolbar already scrolls
              sideways to fit (S7, grill G3, AC-S7-3). Both render the SAME
              `trailing` node - not a re-created copy - so the menu's
              actions stay wired to the exact handlers the inline group
              has. */}
          <div
            data-testid="toolbar-trailing-inline"
            className="ml-auto hidden shrink-0 items-center gap-1 md:flex"
          >
            <Separator orientation="vertical" className="mx-1 h-5 shrink-0" />
            {trailing}
          </div>
          <DropdownMenu>
            <Tooltip delayDuration={300}>
              <TooltipTrigger asChild>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    data-testid="toolbar-trailing-overflow-trigger"
                    className="ml-auto h-8 w-8 shrink-0 p-0 md:hidden"
                  >
                    <MoreHorizontal className="size-4" />
                    <span className="sr-only">More actions</span>
                  </Button>
                </DropdownMenuTrigger>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                More actions
              </TooltipContent>
            </Tooltip>
            <DropdownMenuContent align="end">{trailing}</DropdownMenuContent>
          </DropdownMenu>
        </>
      )}
    </div>
  );
}

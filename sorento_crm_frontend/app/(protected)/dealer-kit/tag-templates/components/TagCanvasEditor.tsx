'use client';

/**
 * Main tag template canvas editor shell.
 *
 * Left sidebar: layers panel. Centre: a Konva Stage that FILLS the workspace,
 * with the artboard drawn at a pan offset inside it (D33). Right sidebar:
 * inspector panel. Top: toolbar.
 *
 * All layer positions and sizes are in mm; the canvas converts to pixels with a
 * zoom-dependent scale. State is local React state, saved on Save.
 *
 * The interaction model is Illustrator's, and the rules behind it are pure
 * functions in `lib/dealer-kit/canvas-geometry.ts`: wheel zooms about the
 * cursor, a select drag on empty space is a marquee, the hand tool (or held
 * Space) pans, a click takes a group and a double-click goes inside it, and a
 * group carries its descendants through every move, transform and clipboard
 * action.
 *
 * The MOUSE BUTTON decides which of those runs (D44). Left marquees, drags and
 * selects; the middle button pans for as long as it is held, whatever tool is
 * active; the right button starts nothing, because the context menu owns it.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import type Konva from 'konva';
import { Konva as KonvaGlobal } from 'konva/lib/Global';
import type {
  GroupBinding,
  ImageSource,
  TagBindingData,
  TagLayer,
  TagLayerProps,
  TagTemplateDoc,
} from '@/lib/dealer-kit/tag-template-types';
import {
  defaultTextProps,
  defaultShapeProps,
  defaultImageProps,
  defaultProductSlotProps,
  defaultPriceBadgeProps,
  defaultBadgeProps,
  defaultBarcodeProps,
} from '@/lib/dealer-kit/tag-template-types';
import {
  buildAccessoriesStrip,
  buildAlternativesRow,
  buildProductBlock,
  buildSetBlock,
  isDynamic,
  layerDisplay,
  rebindImageLayers,
  resolveSlotText,
  PRODUCT_BLOCK_SIZE,
  SET_BLOCK_SIZE,
} from '@/lib/dealer-kit/product-block';
import {
  actualSizeView,
  ancestorsOf,
  bandBetween,
  cloneLayers,
  descendantsOf,
  fitView,
  hitLayerAt,
  marqueeHits,
  moveLayers,
  refitAncestors,
  removeLayers,
  reorderZ,
  reparentLayer,
  stageToMm,
  topmostChildAt,
  transformGroup,
  ungroupLayers,
  zoomAt,
  CANVAS_MAX_ZOOM,
  CANVAS_MIN_ZOOM,
  CANVAS_PX_PER_MM,
  type CanvasView,
  type ReorderDirection,
  type ReparentTarget,
} from '@/lib/dealer-kit/canvas-geometry';
import {
  WHOLE_TAG_BLOCK_ID,
  previewBindingFor,
  previewBlockOf,
  previewableBlocks,
  wholeTagBlock,
  type PreviewMap,
} from '@/lib/dealer-kit/preview';
import { reflowedTextSize } from '@/lib/dealer-kit/text-reflow';
import {
  guideCrossedIntoRuler,
  guideForAxis,
  moveGuide,
  newGuideId,
  placeOrMoveGuide,
  removeGuide,
  type RulerGuide,
} from '@/lib/dealer-kit/ruler-guides';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import {
  ArrowDown,
  ArrowDownToLine,
  ArrowUp,
  ArrowUpToLine,
  ChevronLeft,
  ChevronRight,
  ClipboardPaste,
  Copy,
  CornerLeftUp,
  CornerRightDown,
  Expand,
  Eye,
  EyeOff,
  Group as GroupIcon,
  Lock,
  Percent,
  Scissors,
  SquareDashed,
  Trash2,
  Ungroup,
  Unlock,
  X,
} from 'lucide-react';
import type { ImperativePanelHandle } from 'react-resizable-panels';
import { AssetPickerDialog } from './AssetPickerDialog';
import { FontUploadDialog } from './FontUploadDialog';
import { ProductPickDialog, type PickMode } from './ProductPickDialog';
import { cn } from '@/lib/utils';
import { useKitLibrary, useTagBindings } from './useTagBindings';
import { getProductTagData } from '../../services/tagDataService';
import { CanvasToolbar, type CanvasTool } from './CanvasToolbar';
import { CanvasRulers, RULER_THICKNESS } from './CanvasRulers';
import { LayersPanel } from './LayersPanel';
import { InspectorPanel } from './InspectorPanel';
import { InsertFieldDialog } from './InsertFieldDialog';
import { useCanvasHistory } from './useCanvasHistory';
import { useSnapGuides } from './useSnapGuides';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';
import {
  DEFAULT_PANEL_LAYOUT,
  LEFT_MAX_PX,
  LEFT_MIN_PX,
  RAIL_MIN_PX,
  RIGHT_MAX_PX,
  RIGHT_MIN_PX,
  clampLeft,
  clampRailSplit,
  clampRight,
  readPanelLayout,
  writePanelLayout,
  type PanelLayout,
} from '@/lib/dealer-kit/canvas-panels';
import { toggleBold, toggleTextFlag, type TextFormatFlag } from '@/lib/dealer-kit/text-format';
import { InlineTextEditor } from './InlineTextEditor';

/** What a previewed block is showing, named the way a person reads it. */
interface PreviewChoice {
  id: string;
  label: string;
}

// This component is loaded with ssr:false by the page, so direct imports are safe.
import { Stage, Layer as KonvaLayer, Group, Rect, Line, Transformer } from 'react-konva';
import { KonvaTagLayer } from './KonvaTagLayer';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Konva starts a drag on the middle button as well as the left one by default
// (`dragButtons` ships as `[0, 1]`), so holding the wheel down over a layer
// dragged it while the workspace drew a band. The middle button pans (D44).
KonvaGlobal.dragButtons = [0];

let idCounter = 0;
function newLayerId(): string {
  idCounter += 1;
  return `layer-${Date.now()}-${idCounter}`;
}

/**
 * Whatever is bound, named the way a person recognises it. Never a UUID.
 *
 * One function for the Inspector's "Bound to" line and for the preview chip,
 * because a product that reads one way in one of them and another way in the
 * other is two names for one thing.
 */
function describeBindingData(data: TagBindingData | null | undefined): string | null {
  if (!data) return null;
  if (data.kind === 'product') return `${data.product.code} - ${data.product.name}`;
  if (data.kind === 'set') return `${data.set.set_code} - ${data.set.name}`;
  return `${data.line.code} - ${data.line.name}`;
}

/**
 * The eye chip that opens a block's (or the whole tag's) preview picker
 * (D10, S6). A plain DOM overlay, not a Konva node: it needs to sit ON TOP of
 * the canvas bitmap and stay a normal, focusable, hoverable button, which is
 * cheaper as HTML positioned over the Stage than as a Konva shape faking one.
 *
 * `onMouseEnter`/`onMouseLeave` (B1, AC-S6-4) exist because the chip sits
 * INSIDE the block's own corner: the pointer crossing from the Konva shape
 * onto the chip makes the Stage fire the shape's own `mouseleave` first,
 * which would otherwise unmount this button (nothing else was keeping it
 * shown) before the user's later, separate mousedown for the click ever
 * lands. Reasserting hover on the chip itself keeps it mounted for exactly as
 * long as the pointer is actually over it.
 */
function PreviewEyeButton({
  label,
  active,
  style,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: {
  label: string;
  active: boolean;
  style: React.CSSProperties;
  onClick: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        'absolute z-10 flex h-6 w-6 items-center justify-center rounded-full border bg-background shadow-sm hover:bg-accent',
        active && 'border-primary text-primary',
      )}
      style={style}
      title={label}
      aria-label={label}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      <Eye className="size-3.5" />
    </button>
  );
}

/** One press of the toolbar's zoom buttons. The wheel uses its own factor. */
const ZOOM_BUTTON_FACTOR = 1.25;
/** Pixels the pointer may wander before a click counts as a marquee drag. */
const MARQUEE_SLOP_PX = 3;
/** How far a duplicate or a paste lands from its original, in mm. */
const CLONE_OFFSET_MM = 5;

const ZOOM_LIMITS = { min: CANVAS_MIN_ZOOM, max: CANVAS_MAX_ZOOM };

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface TagCanvasEditorProps {
  doc: TagTemplateDoc;
  onChange: (doc: TagTemplateDoc) => void;
  /**
   * Which promotion the preview prices resolve against. A template is not tied
   * to one, so this is normally absent and the badge previews list prices.
   */
  promotionId?: string | null;
  /**
   * What EVERY layer draws against, when the caller already knows (D51).
   *
   * The request designer edits one line's tag, so the thing on the canvas is
   * that line - resolved once by the pricing engine, with its marketing
   * override applied - rather than whatever each group happens to be bound to.
   * Absent in the template editor, where the document's own bindings answer.
   */
  boundData?: TagBindingData | null;
  /**
   * Anything the host wants above the Layers panel (D51: the request's lines).
   */
  leftRail?: ReactNode;
  /**
   * Every change to the layers, so a host that owns the document can keep up.
   *
   * The template editor does not use it: there, Save is the only moment the
   * document changes. The request designer does, because switching lines
   * remounts the canvas and the edits have to survive that.
   */
  onLayersChange?: (layers: TagLayer[]) => void;
  /** Offered in the Inspector on a selected group: swap the whole tag's template. */
  onUseTemplate?: () => void;
  /** The host owns saving, so the built-in Save bar would be a second Save. */
  hideSaveBar?: boolean;
}

/** What the canvas is currently asking the user to pick. */
type PickerState =
  | { kind: 'none' }
  | { kind: 'add-product' }
  | { kind: 'add-set' }
  | { kind: 'rebind'; groupId: string; mode: PickMode }
  | { kind: 'alternatives' }
  | { kind: 'accessories' }
  | { kind: 'preview'; groupId: string; mode: PickMode };

/** What a drag is carrying, captured once when it starts. */
interface DragSession {
  anchorId: string;
  /** The layers the user grabbed. Descendants come along but are not roots. */
  roots: string[];
  /** Roots plus descendants: everything whose node moves. */
  moving: string[];
  start: Map<string, { x: number; y: number }>;
  dx: number;
  dy: number;
}

export function TagCanvasEditor({
  doc,
  onChange,
  promotionId,
  boundData,
  leftRail,
  onLayersChange,
  onUseTemplate,
  hideSaveBar,
}: TagCanvasEditorProps) {
  const [layers, setLayers] = useState<TagLayer[]>(doc.layers);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  /** The text layer the inline editor (S2, D5) is currently open on, if any. */
  const [editingLayerId, setEditingLayerId] = useState<string | null>(null);
  const [view, setView] = useState<CanvasView>({ zoom: 1, panX: 0, panY: 0 });
  const [tool, setTool] = useState<CanvasTool>('select');
  const [spaceHeld, setSpaceHeld] = useState(false);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
  /**
   * Side-panel widths + collapsed state (S1, D7). Starts at the default so
   * server and first-paint markup match, then hydrates from localStorage -
   * the same trick `useDriveViewMode` uses to avoid a hydration mismatch.
   */
  const [panelLayout, setPanelLayoutState] = useState<PanelLayout>(DEFAULT_PANEL_LAYOUT);
  const [marquee, setMarquee] = useState<{
    x_mm: number;
    y_mm: number;
    width_mm: number;
    height_mm: number;
  } | null>(null);
  const [clipboard, setClipboard] = useState<{ layers: TagLayer[]; roots: string[] } | null>(
    null,
  );
  const [menuOnEmpty, setMenuOnEmpty] = useState(true);
  const [picker, setPicker] = useState<PickerState>({ kind: 'none' });
  const [pickerBusy, setPickerBusy] = useState(false);
  const [imagePicker, setImagePicker] = useState<{ layerId: string; badge: boolean } | null>(
    null,
  );
  const [fontUploadOpen, setFontUploadOpen] = useState(false);
  const [insertFieldOpen, setInsertFieldOpen] = useState(false);
  /** True while the middle button is held: the hand tool, borrowed (D44). */
  const [wheelPanning, setWheelPanning] = useState(false);
  /**
   * What each product BLOCK is DRAWN against while previewing (D53).
   *
   * Keyed by group id, because a tag carries several blocks and they are
   * several different products: the sink combo shows one sink and three
   * alternative taps. A block that is not in the map keeps its placeholders.
   *
   * Editor state only. It is never written into `layers` and Save never sees
   * it, which is the whole point: a template ships unbound so it can be reused
   * for any product in its family, and looking at it with real data must not
   * quietly bind it.
   */
  const [previews, setPreviews] = useState<PreviewMap>({});
  /**
   * The block the on-canvas eye is showing for (S6, D10). Hover only - the
   * SELECTED block reads straight off `selectedBlock` below, no state needed
   * for that half.
   */
  const [hoveredLayerId, setHoveredLayerId] = useState<string | null>(null);
  /**
   * A block's eye chip hovers itself (B1, AC-S6-4): the chip sits inside the
   * block's own corner, so the pointer crossing onto it makes the Stage fire
   * the block's `mouseleave` first. Without this, `hoveredLayerId` clearing
   * would unmount the chip before the click that followed the hover ever
   * landed - the whole point of `activeCanvasEyeBlockId` falling back to this
   * below.
   */
  const [chipHoveredBlockId, setChipHoveredBlockId] = useState<string | null>(null);
  /** Session-only ruler guides (D9/D17). Never touch the document. */
  const [rulerGuides, setRulerGuides] = useState<RulerGuide[]>([]);
  /**
   * The one guide, if any, currently selected for Delete/Backspace (D21,
   * AC-S8-2) - a plain click on it (not a drag) is what sets this. Kept
   * separate from `selectedIds` (layer selection): the two are mutually
   * exclusive, and mixing a guide id into that Set would make the Transformer
   * try to attach to it.
   */
  const [selectedGuideId, setSelectedGuideId] = useState<string | null>(null);

  const bindings = useTagBindings(promotionId);
  const library = useKitLibrary();

  const containerRef = useRef<HTMLDivElement>(null);
  /** The whole [left][canvas][right] row, measured to convert px <-> % (S1). */
  const panelGroupRef = useRef<HTMLDivElement>(null);
  const [panelGroupSize, setPanelGroupSize] = useState({ width: 0, height: 0 });
  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  const rightPanelRef = useRef<ImperativePanelHandle>(null);
  const stageRef = useRef<Konva.Stage | null>(null);
  const transformerRef = useRef<Konva.Transformer>(null);
  const dragRef = useRef<DragSession | null>(null);
  const panRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const marqueeRef = useRef<{
    start: { x_mm: number; y_mm: number };
    additive: boolean;
  } | null>(null);
  const fittedRef = useRef(false);
  /**
   * Which guide a pointer drag is currently moving, if any (S6, B2).
   *
   * `moved` distinguishes a genuine drag from a plain click, the same way
   * `MARQUEE_SLOP_PX` does for the marquee below: it only flips once the
   * pointer has wandered past the slop from `downClient`, not on the very
   * first `mousemove` tick. A freshly-dropped guide sits INSIDE ruler
   * territory by construction (that is where the ruler's own mousedown put
   * it) - without the slop, the sub-pixel jitter every real click carries set
   * `moved` on tick one, and the guide deleted itself on mouseup for having
   * never actually left the ruler.
   *
   * `leftRuler` is the second half: only a drag that has genuinely LEFT ruler
   * territory at some point counts as "dragged back onto the ruler" on
   * release. A newly-spawned guide starts inside the ruler and so starts
   * `false`; a guide picked up off the canvas starts outside it and so starts
   * `true` - it can be sent home on the very first re-entry, exactly as
   * before.
   */
  const guideDragRef = useRef<{
    id: string;
    orientation: RulerGuide['orientation'];
    moved: boolean;
    leftRuler: boolean;
    downClient: { x: number; y: number };
  } | null>(null);

  const history = useCanvasHistory(doc.layers);
  const { computeSnap, guides, clearGuides } = useSnapGuides();

  const scale = CANVAS_PX_PER_MM * view.zoom;
  const canvasWidthPx = doc.width_mm * scale;
  const canvasHeightPx = doc.height_mm * scale;
  const stageWidth = Math.max(0, containerSize.width - RULER_THICKNESS);
  const stageHeight = Math.max(0, containerSize.height - RULER_THICKNESS);
  /** The hand tool, whether chosen or borrowed by holding Space (D35). */
  const handMode = tool === 'hand' || spaceHeld;

  // -- Commit ----------------------------------------------------------------

  /** One state write and one history entry, so one undo reverts one action. */
  const commit = useCallback(
    (next: TagLayer[], nextSelection?: Set<string>) => {
      setLayers(next);
      history.pushState(next);
      if (nextSelection) setSelectedIds(nextSelection);
    },
    [history],
  );

  // -- Layer mutations -------------------------------------------------------

  const updateLayer = useCallback(
    (id: string, changes: Partial<TagLayer>) => {
      setLayers((prev) => {
        const layer = prev.find((l) => l.id === id);
        const geometric = (
          ['x_mm', 'y_mm', 'width_mm', 'height_mm', 'rotation_deg'] as const
        ).some((key) => key in changes);

        let next: TagLayer[];
        if (layer && layer.props.kind === 'group' && geometric) {
          // The inspector's X/Y/W/H on a group means the whole block (D38).
          next = transformGroup(prev, id, {
            x_mm: changes.x_mm ?? layer.x_mm,
            y_mm: changes.y_mm ?? layer.y_mm,
            width_mm: changes.width_mm ?? layer.width_mm,
            height_mm: changes.height_mm ?? layer.height_mm,
            rotation_deg: changes.rotation_deg ?? layer.rotation_deg,
          }).map((l) => (l.id === id ? { ...l, ...changes } : l));
        } else {
          next = prev.map((l) => (l.id === id ? { ...l, ...changes } : l));
          if (geometric) next = refitAncestors(next, id);
        }
        history.pushState(next);
        return next;
      });
    },
    [history],
  );

  const updateLayerProps = useCallback(
    (id: string, propsChanges: Partial<TagLayerProps>) => {
      setLayers((prev) => {
        const next = prev.map((l) =>
          l.id === id ? { ...l, props: { ...l.props, ...propsChanges } as TagLayerProps } : l,
        );
        history.pushState(next);
        return next;
      });
    },
    [history],
  );

  /**
   * B/I/U/Shift+X (S2, D4): applied to every selected TEXT layer at once, one
   * history entry, all landing on the same target state (AC-S2-4) - a mixed
   * selection turns the flag ON, an all-set selection turns it OFF. Bold is
   * `fontWeight`, not a boolean, so it gets its own branch using the same
   * "already bold" reading (>= 600) `toggleBold` itself uses per layer.
   */
  const applyTextFormat = useCallback(
    (flag: 'bold' | TextFormatFlag) => {
      const targetIds = Array.from(selectedIds).filter(
        (id) => layers.find((l) => l.id === id)?.props.kind === 'text',
      );
      if (targetIds.length === 0) return;

      if (flag === 'bold') {
        const targeted = layers.filter((l) => targetIds.includes(l.id));
        const allBold = targeted.every(
          (l) => (l.props as Extract<TagLayerProps, { kind: 'text' }>).fontWeight >= 600,
        );
        const nextWeight = toggleBold(allBold ? 600 : 400);
        commit(
          layers.map((l) =>
            targetIds.includes(l.id) && l.props.kind === 'text'
              ? { ...l, props: { ...l.props, fontWeight: nextWeight } }
              : l,
          ),
        );
        return;
      }

      commit(toggleTextFlag(layers, targetIds, flag));
    },
    [layers, selectedIds, commit],
  );

  const addLayer = useCallback(
    (layer: TagLayer) => {
      setLayers((prev) => {
        const next = [...prev, layer];
        history.pushState(next);
        return next;
      });
      setSelectedIds(new Set([layer.id]));
    },
    [history],
  );

  const addLayers = useCallback(
    (incoming: TagLayer[]) => {
      if (incoming.length === 0) return;
      setLayers((prev) => {
        const next = [...prev, ...incoming];
        history.pushState(next);
        return next;
      });
      // The GROUP is what gets selected when a block is dropped, so the
      // inspector opens on the binding rather than on whichever child happened
      // to be last.
      const group = incoming.find((layer) => layer.props.kind === 'group');
      setSelectedIds(new Set([group ? group.id : incoming[incoming.length - 1].id]));
    },
    [history],
  );

  /** The selected ids with no selected ancestor: one entry per grabbed block. */
  const selectionRoots = useMemo(() => {
    const ids = Array.from(selectedIds);
    return ids.filter((id) => !ancestorsOf(layers, id).some((a) => selectedIds.has(a)));
  }, [selectedIds, layers]);

  const deleteSelectedLayers = useCallback(() => {
    if (selectionRoots.length === 0) return;
    commit(removeLayers(layers, selectionRoots), new Set());
  }, [selectionRoots, layers, commit]);

  const duplicateSelectedLayers = useCallback(() => {
    if (selectionRoots.length === 0) return;
    const cloned = cloneLayers(layers, selectionRoots, newLayerId, CLONE_OFFSET_MM);
    if (cloned.layers.length === 0) return;
    commit([...layers, ...cloned.layers], new Set(cloned.ids));
  }, [selectionRoots, layers, commit]);

  const groupSelectedLayers = useCallback(() => {
    if (selectionRoots.length < 2) return;
    const children = layers.filter((l) => selectionRoots.includes(l.id));
    if (children.length < 2) return;

    const minX = Math.min(...children.map((l) => l.x_mm));
    const minY = Math.min(...children.map((l) => l.y_mm));
    const maxX = Math.max(...children.map((l) => l.x_mm + l.width_mm));
    const maxY = Math.max(...children.map((l) => l.y_mm + l.height_mm));
    const maxZ = Math.max(...layers.map((l) => l.z_index)) + 1;

    const groupId = newLayerId();
    const groupLayer: TagLayer = {
      id: groupId,
      type: 'group',
      x_mm: minX,
      y_mm: minY,
      width_mm: maxX - minX,
      height_mm: maxY - minY,
      rotation_deg: 0,
      z_index: maxZ,
      locked: false,
      visible: true,
      slot_binding: null,
      text_override: null,
      props: { kind: 'group', children: children.map((l) => l.id) },
    };

    commit([...layers, groupLayer], new Set([groupId]));
  }, [selectionRoots, layers, commit]);

  const ungroupSelectedLayers = useCallback(() => {
    const groupIds = layers
      .filter((l) => selectedIds.has(l.id) && l.props.kind === 'group')
      .map((l) => l.id);
    if (groupIds.length === 0) return;
    const result = ungroupLayers(layers, groupIds);
    commit(result.layers, new Set(result.ids));
  }, [selectedIds, layers, commit]);

  const reorderSelection = useCallback(
    (direction: ReorderDirection) => {
      if (selectionRoots.length === 0) return;
      commit(reorderZ(layers, selectionRoots, direction));
    },
    [selectionRoots, layers, commit],
  );

  /** Nudge the whole selection at once, so a group and a child move once each. */
  const nudgeSelection = useCallback(
    (dx_mm: number, dy_mm: number) => {
      const movable = selectionRoots.filter(
        (id) => !layers.find((l) => l.id === id)?.locked,
      );
      if (movable.length === 0) return;
      let next = moveLayers(layers, movable, dx_mm, dy_mm);
      for (const id of movable) next = refitAncestors(next, id);
      commit(next);
    },
    [selectionRoots, layers, commit],
  );

  // -- Add layer factories ---------------------------------------------------

  const centerX = doc.width_mm / 2;
  const centerY = doc.height_mm / 2;
  const maxZ = useMemo(
    () => (layers.length > 0 ? Math.max(...layers.map((l) => l.z_index)) + 1 : 1),
    [layers],
  );

  // -- Bound data ------------------------------------------------------------

  /** childId -> the group that owns it, so a layer can find its binding. */
  const groupOfChild = useMemo(() => {
    const map = new Map<string, TagLayer>();
    for (const layer of layers) {
      if (layer.props.kind !== 'group') continue;
      for (const childId of layer.props.children) map.set(childId, layer);
    }
    return map;
  }, [layers]);

  const bindingOf = useCallback(
    (layer: TagLayer): GroupBinding | undefined => {
      // The preview of the layer's own BLOCK wins (D53), then whatever the
      // document binds. Asking the document first would leave every slot empty
      // on a template, which ships unbound on purpose.
      const previewed = previewBindingFor(layer, previews, groupOfChild);
      if (previewed) return previewed;
      if (layer.props.kind === 'group') return layer.props.binding ?? undefined;
      const group = groupOfChild.get(layer.id);
      return group && group.props.kind === 'group'
        ? group.props.binding ?? undefined
        : undefined;
    },
    [groupOfChild, previews],
  );

  const dataOf = useCallback(
    (layer: TagLayer) => {
      // A previewed block is the deliberate "show me this other thing", so it
      // outranks even the data the host handed in (D51). Per layer rather than
      // per canvas: previewing ONE block of a request's tag must not blank the
      // rest of it.
      const previewed = previewBindingFor(layer, previews, groupOfChild);
      if (previewed) return bindings.get(previewed);
      if (boundData) return boundData;
      return bindings.get(bindingOf(layer));
    },
    [bindings, bindingOf, boundData, groupOfChild, previews],
  );

  // Resolve whatever the document already carries, once, on open. A template
  // stores bindings and no values (ADR 0008), so without this every bound layer
  // would open showing the text it was created with.
  useEffect(() => {
    // Nothing to resolve when the host hands the data in: the bindings would
    // be fetched only to be ignored by `dataOf`.
    if (boundData) return;
    const carried = doc.layers
      .map((layer) => (layer.props.kind === 'group' ? layer.props.binding : undefined))
      .filter((binding): binding is GroupBinding => Boolean(binding));
    if (carried.length > 0) void bindings.loadAll(carried);
    // Deliberately once per document: re-running on every layer change would
    // re-fetch the whole catalogue on each drag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc]);

  const makeBaseLayer = useCallback(
    (type: TagLayer['type'], width: number, height: number): Omit<TagLayer, 'props'> => ({
      id: newLayerId(),
      type,
      x_mm: centerX - width / 2,
      y_mm: centerY - height / 2,
      width_mm: width,
      height_mm: height,
      rotation_deg: 0,
      z_index: maxZ,
      locked: false,
      visible: true,
      slot_binding: null,
      text_override: null,
    }),
    [centerX, centerY, maxZ],
  );

  const handleAddText = useCallback(() => {
    addLayer({ ...makeBaseLayer('text', 40, 10), props: defaultTextProps() });
  }, [addLayer, makeBaseLayer]);

  const handleAddShape = useCallback(() => {
    addLayer({ ...makeBaseLayer('shape', 30, 20), props: defaultShapeProps() });
  }, [addLayer, makeBaseLayer]);

  const handleAddImage = useCallback(() => {
    addLayer({ ...makeBaseLayer('image', 40, 30), props: defaultImageProps() });
  }, [addLayer, makeBaseLayer]);

  const handleAddProductSlot = useCallback(() => {
    addLayer({
      ...makeBaseLayer('product_slot', 40, 30),
      props: defaultProductSlotProps(),
    });
  }, [addLayer, makeBaseLayer]);

  const handleAddPriceBadge = useCallback(() => {
    addLayer({
      ...makeBaseLayer('price_badge', 45, 17),
      props: defaultPriceBadgeProps(),
    });
  }, [addLayer, makeBaseLayer]);

  const handleAddBadge = useCallback(() => {
    const layer = { ...makeBaseLayer('badge', 15, 15), props: defaultBadgeProps() };
    addLayer(layer);
    // Straight into the picker: a badge with no artwork is an empty square, and
    // the reason somebody pressed the button was to place a specific badge.
    setImagePicker({ layerId: layer.id, badge: true });
  }, [addLayer, makeBaseLayer]);

  const handleAddBarcode = useCallback(() => {
    // Bound to slot 'barcode' on creation, not left null like the generic
    // layer types: there is only one thing a barcode layer could ever draw
    // (the tag's own product), so there is no picker step to go through (S7).
    addLayer({
      ...makeBaseLayer('barcode', 40, 22),
      slot_binding: 'barcode',
      props: defaultBarcodeProps(),
    });
  }, [addLayer, makeBaseLayer]);

  // -- Bound blocks (D27) and preview (D41) ----------------------------------

  const closePicker = useCallback(() => {
    setPicker({ kind: 'none' });
    setPickerBusy(false);
  }, []);

  /**
   * The blocks the user may preview, and what each of them wants (D53).
   *
   * Read off the layers rather than off a binding, because a template carries
   * no binding: a `set_members` slot is the document saying what it is for.
   */
  const previewBlocks = useMemo(() => previewableBlocks(layers), [layers]);

  /**
   * ONE implicit block over every loose (ungrouped) bound layer (D10, S6).
   * Its eye lives on the tag frame rather than on any single layer - there is
   * no group to put it on.
   */
  const wholeTagPreviewBlock = useMemo(() => wholeTagBlock(layers), [layers]);

  /** Every block with its own eye - the real ones plus the frame's, if any. */
  const allPreviewBlocks = useMemo(
    () => (wholeTagPreviewBlock ? [...previewBlocks, wholeTagPreviewBlock] : previewBlocks),
    [previewBlocks, wholeTagPreviewBlock],
  );

  /**
   * One block's eye, from anywhere it is shown - the canvas chip, the
   * Inspector, or the tag frame (D10, S6): all three open the same
   * single-question picker aimed at that block.
   */
  const openBlockPreview = useCallback(
    (groupId: string) => {
      const block = allPreviewBlocks.find((b) => b.groupId === groupId);
      if (!block) return;
      setPicker({ kind: 'preview', groupId: block.groupId, mode: block.mode });
    },
    [allPreviewBlocks],
  );

  const clearBlockPreview = useCallback((groupId: string) => {
    setPreviews((prev) => {
      const next = { ...prev };
      delete next[groupId];
      return next;
    });
  }, []);

  const handlePick = useCallback(
    async (ids: string[]) => {
      if (ids.length === 0) return;
      setPickerBusy(true);
      try {
        if (picker.kind === 'add-product') {
          const product = await bindings.loadProduct(ids[0]);
          if (!product) return;
          addLayers(
            buildProductBlock(product, {
              newId: newLayerId,
              x_mm: Math.max(0, centerX - PRODUCT_BLOCK_SIZE.width_mm / 2),
              y_mm: Math.max(0, centerY - PRODUCT_BLOCK_SIZE.height_mm / 2),
              z_index: maxZ,
            }),
          );
        } else if (picker.kind === 'add-set') {
          const set = await bindings.loadSet(ids[0]);
          if (!set) return;
          addLayers(
            buildSetBlock(set, {
              newId: newLayerId,
              x_mm: Math.max(0, centerX - SET_BLOCK_SIZE.width_mm / 2),
              y_mm: Math.max(0, centerY - SET_BLOCK_SIZE.height_mm / 2),
              z_index: maxZ,
            }),
          );
        } else if (picker.kind === 'preview') {
          const isSet = picker.mode === 'set';
          const groupId = picker.groupId;
          const loaded = isSet
            ? await bindings.loadSet(ids[0])
            : await bindings.loadProduct(ids[0]);
          if (!loaded) return;
          setPreviews((prev) => ({
            ...prev,
            [groupId]: isSet ? { product_set_id: ids[0] } : { product_id: ids[0] },
          }));
        } else if (picker.kind === 'alternatives') {
          const products = [];
          for (const id of ids) {
            const product = await getProductTagData(id, promotionId ?? null);
            products.push(product);
          }
          addLayers(
            buildAlternativesRow(products, {
              newId: newLayerId,
              x_mm: 5,
              y_mm: Math.max(0, centerY),
              z_index: maxZ,
            }),
          );
        } else if (picker.kind === 'accessories') {
          const items = [];
          for (const id of ids) {
            const product = await getProductTagData(id, promotionId ?? null);
            const primary =
              product.images.find((image) => image.is_primary) ?? product.images[0];
            items.push({
              caption: product.code,
              source: primary
                ? ({
                    type: 'product_attachment' as const,
                    attachmentId: primary.attachment_id,
                  })
                : null,
            });
          }
          addLayers(
            buildAccessoriesStrip(items, {
              newId: newLayerId,
              x_mm: 5,
              y_mm: Math.max(0, centerY),
              z_index: maxZ,
            }),
          );
        } else if (picker.kind === 'rebind') {
          const groupId = picker.groupId;
          const isSet = picker.mode === 'set';

          // The block's binding moves; its layout and any typed-over text stay.
          const product = isSet ? null : await bindings.loadProduct(ids[0]);
          const set = isSet ? await bindings.loadSet(ids[0]) : null;
          if (!product && !set) return;

          const group = layers.find((layer) => layer.id === groupId);
          const childIds = new Set(
            group && group.props.kind === 'group' ? group.props.children : [],
          );
          const binding: GroupBinding = isSet
            ? { product_set_id: ids[0] }
            : { product_id: ids[0] };

          setLayers((prev) => {
            const rebound = prev.map((layer) =>
              layer.id === groupId && layer.props.kind === 'group'
                ? { ...layer, props: { ...layer.props, binding } }
                : layer,
            );
            // An image layer still holding the old product's attachment id
            // would print the wrong photo under the right name.
            const next = product
              ? rebindImageLayers(rebound, childIds, { kind: 'product', product })
              : rebound;
            history.pushState(next);
            return next;
          });
        }
        closePicker();
      } finally {
        setPickerBusy(false);
      }
    },
    [
      picker,
      bindings,
      addLayers,
      centerX,
      centerY,
      maxZ,
      layers,
      history,
      promotionId,
      closePicker,
    ],
  );

  const handleRebind = useCallback(
    (groupId: string) => {
      const group = layers.find((layer) => layer.id === groupId);
      const binding =
        group && group.props.kind === 'group' ? group.props.binding : undefined;

      // What the block is FOR, not only what it already holds. Asking the
      // binding alone works for a block the editor built - "Add set" leaves a
      // set id behind - but not for a TEMPLATE, which ships unbound on purpose:
      // the seeded bathroom-furniture tag is entirely about a set, and it could
      // only ever be offered a product picker, so the one thing it exists to be
      // bound to was unreachable. A `set_members` slot is the block saying so.
      const childIds =
        group && group.props.kind === 'group' ? new Set(group.props.children) : null;
      const aboutASet =
        Boolean(binding?.product_set_id) ||
        (childIds != null &&
          layers.some(
            (layer) => childIds.has(layer.id) && layer.slot_binding === 'set_members',
          ));

      setPicker({
        kind: 'rebind',
        groupId,
        mode: aboutASet ? 'set' : 'product',
      });
    },
    [layers],
  );

  /** Put every typed-over layer in this block back on the product's own words. */
  const handleRelinkGroup = useCallback(
    (groupId: string) => {
      const group = layers.find((layer) => layer.id === groupId);
      if (!group || group.props.kind !== 'group') return;
      const childIds = new Set(group.props.children);
      setLayers((prev) => {
        const next = prev.map((layer) =>
          // A dynamic layer is skipped (D57): its override holds merge fields,
          // so it already draws from the product, and clearing it would delete
          // the sentence somebody wrote rather than repair a broken link.
          childIds.has(layer.id) && layer.slot_binding && !isDynamic(layer)
            ? { ...layer, text_override: null }
            : layer,
        );
        history.pushState(next);
        return next;
      });
    },
    [layers, history],
  );

  const handleChooseImage = useCallback((layerId: string) => {
    setImagePicker({ layerId, badge: false });
  }, []);

  const handleChooseBadge = useCallback((layerId: string) => {
    setImagePicker({ layerId, badge: true });
  }, []);

  const handleImagePicked = useCallback(
    (source: ImageSource) => {
      const target = imagePicker;
      if (!target) return;
      setLayers((prev) => {
        const next = prev.map((layer) => {
          if (layer.id !== target.layerId) return layer;
          if (layer.props.kind === 'badge') {
            if (source.type !== 'asset') return layer;
            return { ...layer, props: { ...layer.props, assetId: source.assetId } };
          }
          if (layer.props.kind === 'image') {
            return { ...layer, props: { ...layer.props, source } };
          }
          return layer;
        });
        history.pushState(next);
        return next;
      });
      // A freshly uploaded asset is not in the library map yet, so refresh it or
      // the layer draws its no-image state until the next open.
      void library.reload();
      setImagePicker(null);
    },
    [imagePicker, history, library],
  );

  // -- Selection and group isolation (D37) -----------------------------------

  /**
   * The groups the user is inside, derived from the selection rather than
   * stored: every ancestor of every selected layer. Nothing to keep in step
   * with undo, redo or a Layers panel click, because there is no second copy.
   */
  const entered = useMemo(() => {
    const set = new Set<string>();
    for (const id of selectedIds) {
      for (const ancestorId of ancestorsOf(layers, id)) set.add(ancestorId);
    }
    return set;
  }, [selectedIds, layers]);

  /** The innermost group being edited, which scopes a marquee (D36). */
  const insideGroupId = useMemo(() => {
    const first = Array.from(selectedIds)[0];
    if (!first) return null;
    return ancestorsOf(layers, first)[0] ?? null;
  }, [selectedIds, layers]);

  /** A raw canvas hit, answered at the level the user is working at. */
  const resolveTarget = useCallback(
    (rawId: string) => {
      const chain = [...ancestorsOf(layers, rawId)].reverse();
      for (const ancestorId of chain) {
        if (!entered.has(ancestorId)) return ancestorId;
      }
      return rawId;
    },
    [layers, entered],
  );

  /** Layers panel and inspector: pick exactly what was asked for. */
  const handleSelect = useCallback((id: string, additive: boolean) => {
    // Selecting a LAYER deselects the guide (B4). The two selections share one
    // Delete key, so leaving both live makes what that key removes depend on
    // an order the user cannot see.
    setSelectedGuideId(null);
    setSelectedIds((prev) => {
      if (additive) {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }
      return new Set([id]);
    });
  }, []);

  const handleCanvasSelect = useCallback(
    (rawId: string, additive: boolean) => {
      const id = resolveTarget(rawId);
      setSelectedGuideId(null);
      setSelectedIds((prev) => {
        if (additive) {
          const next = new Set(prev);
          if (next.has(id)) next.delete(id);
          else next.add(id);
          return next;
        }
        // Grabbing something already selected keeps the multi-selection, so it
        // can be dragged as one.
        if (prev.has(id)) return prev;
        return new Set([id]);
      });
    },
    [resolveTarget],
  );

  const pointerMm = useCallback(() => {
    const point = stageRef.current?.getPointerPosition();
    return point ? stageToMm(view, point.x, point.y) : null;
  }, [view]);

  /**
   * A layer's own hover state (S6, D10) - not yet resolved to a BLOCK, which
   * `hoveredBlockId` below does: hovering any child of a block should reveal
   * its eye, and that resolution belongs with the other block bookkeeping,
   * not here.
   */
  const handleLayerHoverChange = useCallback((id: string, hovering: boolean) => {
    setHoveredLayerId((prev) => {
      if (hovering) return id;
      return prev === id ? null : prev;
    });
  }, []);

  /** A block's own eye chip re-asserting its hover (B1, AC-S6-4). */
  const handleChipHoverChange = useCallback((groupId: string, hovering: boolean) => {
    setChipHoveredBlockId((prev) => {
      if (hovering) return groupId;
      return prev === groupId ? null : prev;
    });
  }, []);

  const handleLayerDoubleClick = useCallback(
    (rawId: string) => {
      const targetId = resolveTarget(rawId);
      const target = layers.find((layer) => layer.id === targetId);
      if (!target) return;
      // A text layer opens the inline editor in place (S2, D5); a group still
      // steps a level in, exactly as before.
      if (target.props.kind === 'text') {
        setSelectedIds(new Set([target.id]));
        setEditingLayerId(target.id);
        return;
      }
      if (target.props.kind !== 'group') return;
      const point = pointerMm();
      const childId = point
        ? topmostChildAt(layers, targetId, point.x_mm, point.y_mm)
        : null;
      const fallback = target.props.children.find((id) =>
        layers.some((layer) => layer.id === id),
      );
      const pick = childId ?? fallback;
      if (pick) setSelectedIds(new Set([pick]));
    },
    [layers, resolveTarget, pointerMm],
  );

  /** Escape climbs one level, and deselects at the top. */
  const selectParentGroup = useCallback(() => {
    const first = Array.from(selectedIds)[0];
    const parent = first ? ancestorsOf(layers, first)[0] : null;
    setSelectedIds(parent ? new Set([parent]) : new Set());
  }, [selectedIds, layers]);

  const enterSelectedGroup = useCallback(() => {
    const first = Array.from(selectedIds)[0];
    const group = first ? layers.find((layer) => layer.id === first) : null;
    if (!group || group.props.kind !== 'group') return;
    const child = group.props.children.find((id) => layers.some((l) => l.id === id));
    if (child) setSelectedIds(new Set([child]));
  }, [selectedIds, layers]);

  const selectAll = useCallback(() => {
    const parented = new Set<string>();
    for (const layer of layers) {
      if (layer.props.kind !== 'group') continue;
      for (const childId of layer.props.children) parented.add(childId);
    }
    setSelectedIds(
      new Set(
        layers
          .filter((layer) => !parented.has(layer.id) && layer.visible && !layer.locked)
          .map((layer) => layer.id),
      ),
    );
  }, [layers]);

  // -- Drag and snap (D38) ---------------------------------------------------

  const handleDragStart = useCallback(
    (id: string) => {
      const roots = selectedIds.has(id) ? selectionRoots : [id];
      const moving = new Set<string>();
      for (const rootId of roots) {
        moving.add(rootId);
        for (const childId of descendantsOf(layers, rootId)) moving.add(childId);
      }
      const start = new Map<string, { x: number; y: number }>();
      for (const layer of layers) {
        if (moving.has(layer.id)) start.set(layer.id, { x: layer.x_mm, y: layer.y_mm });
      }
      dragRef.current = {
        anchorId: id,
        roots: [...roots],
        moving: Array.from(moving),
        start,
        dx: 0,
        dy: 0,
      };
    },
    [selectedIds, selectionRoots, layers],
  );

  /** Ruler guide positions, split by axis, so a drag can also snap to them (D9). */
  const guideSnapTargets = useMemo(
    () => ({
      vertical: rulerGuides
        .filter((g) => g.orientation === 'vertical')
        .map((g) => g.position_mm),
      horizontal: rulerGuides
        .filter((g) => g.orientation === 'horizontal')
        .map((g) => g.position_mm),
    }),
    [rulerGuides],
  );

  /** The axis's own one guide (D21) - what the ruler's x chip draws at. */
  const verticalGuide = useMemo(() => guideForAxis(rulerGuides, 'vertical'), [rulerGuides]);
  const horizontalGuide = useMemo(() => guideForAxis(rulerGuides, 'horizontal'), [rulerGuides]);

  const handleDragMove = useCallback(
    (id: string, rawX: number, rawY: number) => {
      const drag = dragRef.current;
      if (!drag || drag.anchorId !== id) return;
      const anchorStart = drag.start.get(id);
      const layer = layers.find((l) => l.id === id);
      if (!anchorStart || !layer) return;

      // Everything travelling with the pointer is excluded from the snap
      // targets, or a group would latch onto its own children on every pixel.
      const movingSet = new Set(drag.moving);
      const result = computeSnap(
        id,
        rawX,
        rawY,
        layer.width_mm,
        layer.height_mm,
        layers.filter((l) => !movingSet.has(l.id)),
        doc.width_mm,
        doc.height_mm,
        guideSnapTargets,
      );
      drag.dx = result.x_mm - anchorStart.x;
      drag.dy = result.y_mm - anchorStart.y;

      const stage = stageRef.current;
      if (!stage) return;
      for (const memberId of drag.moving) {
        const from = drag.start.get(memberId);
        if (!from) continue;
        const node = stage.findOne(`#${memberId}`);
        if (!node) continue;
        node.x((from.x + drag.dx) * scale);
        node.y((from.y + drag.dy) * scale);
      }
    },
    [layers, computeSnap, doc.width_mm, doc.height_mm, scale, guideSnapTargets],
  );

  const handleDragEnd = useCallback(
    (id: string) => {
      clearGuides();
      const drag = dragRef.current;
      dragRef.current = null;
      if (!drag || drag.anchorId !== id) return;
      if (drag.dx === 0 && drag.dy === 0) return;

      let next = moveLayers(layers, drag.roots, drag.dx, drag.dy);
      for (const rootId of drag.roots) next = refitAncestors(next, rootId);
      commit(next);
    },
    [clearGuides, layers, commit],
  );

  // -- Transform (D38) -------------------------------------------------------

  // ONE Transformer for the whole selection. Attaching happens after render, so
  // the nodes it is given exist and carry the ids `KonvaTagLayer` now sets.
  useEffect(() => {
    const transformer = transformerRef.current;
    const stage = stageRef.current;
    if (!transformer || !stage) return;
    const nodes = Array.from(selectedIds)
      .map((id) => layers.find((layer) => layer.id === id))
      .filter((layer): layer is TagLayer => Boolean(layer) && !layer!.locked && layer!.visible)
      .map((layer) => stage.findOne(`#${layer.id}`))
      .filter((node): node is Konva.Node => Boolean(node));
    transformer.nodes(nodes);
    transformer.getLayer()?.batchDraw();
  }, [selectedIds, layers, scale, view]);

  /**
   * Live reflow while a TEXT layer is being resized (D8, S6).
   *
   * Fires on every `onTransform` tick, not just at the end. A text node's
   * Group sits at a fixed `width`/`height` (the layer's own mm size, in px)
   * until `handleTransformEnd` commits a new one; in between, Konva expresses
   * the drag as a `scale` on that Group, which stretches the fixed-size Text
   * child inside it along with everything else - the font visibly balloons or
   * shrinks for the whole drag and only snaps back to its real size on
   * release. Reading that scale here, folding it into the Group's AND the
   * Text child's own `width`/`height`, and resetting the scale to 1 makes
   * Konva re-wrap the text at its real, UNCHANGED `fontSize` on every frame
   * instead: the box reflows live, the font never moves.
   *
   * Only text nodes get this. A GROUP's own Konva node is just its dashed
   * outline (`KonvaTagLayer`'s children render as separate, flat siblings,
   * not nested inside it) - resizing it live here would touch nothing a user
   * can see, and `transformGroup`'s redistribution to every descendant still
   * has to wait for `handleTransformEnd`, exactly as before.
   *
   * Konva's Transformer fires its own `transform` event once per ATTACHED
   * NODE on every tick, not once (`_fitNodesInto` loops `this._nodes` and
   * fires on each) - so with N selected layers this callback itself runs N
   * times per tick, and each run already loops every selected node again
   * (N4). The guard below collapses that back to one pass: the first call in
   * a tick does the work and schedules a microtask to clear itself, and every
   * other call in the SAME synchronous batch of `_fire`s - which is all of
   * them, since `_fitNodesInto` never yields between them - sees the guard
   * still set and returns immediately.
   */
  const transformTickRef = useRef(false);

  const handleTransform = useCallback(() => {
    if (transformTickRef.current) return;
    transformTickRef.current = true;
    queueMicrotask(() => {
      transformTickRef.current = false;
    });

    const transformer = transformerRef.current;
    if (!transformer) return;
    for (const node of transformer.nodes()) {
      const layer = layers.find((l) => l.id === node.id());
      if (!layer || layer.props.kind !== 'text') continue;
      const { width, height } = reflowedTextSize(
        node.width(),
        node.height(),
        node.scaleX(),
        node.scaleY(),
      );
      node.scaleX(1);
      node.scaleY(1);
      node.width(width);
      node.height(height);
      // `KonvaTagLayer` always renders a text layer as `<Group><Text/></Group>`,
      // so this cast is safe for exactly the nodes reaching this branch -
      // `findOne` only exists on a Container, and `Konva.Node` (what
      // `transformer.nodes()` is typed as) is not one.
      const textNode = (node as unknown as Konva.Group).findOne('Text');
      if (textNode) {
        textNode.width(width);
        textNode.height(height);
      }
    }
    transformer.getLayer()?.batchDraw();
  }, [layers]);

  const handleTransformEnd = useCallback(() => {
    const transformer = transformerRef.current;
    if (!transformer) return;

    // Read and reset the Konva scale BEFORE touching state: a React updater can
    // run twice, and a second read would see the already-reset scale and undo
    // the resize. `handleTransform` above has already zeroed a text node's
    // scale on the last live tick, so this reads 1 for one - and runs the
    // SAME `reflowedTextSize` fold either way (N3), so text and non-text
    // really do share one commit path rather than a comment merely claiming
    // they do.
    const changes = transformer.nodes().map((node) => {
      const scaleX = node.scaleX();
      const scaleY = node.scaleY();
      node.scaleX(1);
      node.scaleY(1);
      const { width, height } = reflowedTextSize(node.width(), node.height(), scaleX, scaleY);
      return {
        id: node.id(),
        attrs: {
          x_mm: node.x() / scale,
          y_mm: node.y() / scale,
          width_mm: width / scale,
          height_mm: height / scale,
          rotation_deg: node.rotation(),
        },
      };
    });

    let next = layers;
    for (const { id, attrs } of changes) {
      const layer = next.find((l) => l.id === id);
      if (!layer) continue;
      if (layer.props.kind === 'group') {
        next = transformGroup(next, id, attrs);
      } else {
        next = refitAncestors(
          next.map((l) => (l.id === id ? { ...l, ...attrs } : l)),
          id,
        );
      }
    }
    commit(next);
  }, [layers, scale, commit]);

  // -- Ruler guides (D9/D17, S6) ----------------------------------------------

  /** The stage-relative pixel a client (viewport) point falls on. */
  const stagePointFromClient = useCallback((clientX: number, clientY: number) => {
    const element = containerRef.current;
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return {
      x: clientX - rect.left - RULER_THICKNESS,
      y: clientY - rect.top - RULER_THICKNESS,
    };
  }, []);

  /**
   * A guide-drop gesture started on a ruler (D9/D17). The guide is placed (or,
   * if that axis already has one, MOVED - D21, AC-S8-1) IMMEDIATELY, right
   * where the pointer went down - a plain click needs no separate "drop"
   * step - and `guideDragRef` hands the rest of the gesture to the same
   * window-level listener an existing guide's own drag reuses below, so a
   * click that is followed by movement smoothly turns into a pull-out
   * without two code paths to keep in sync.
   */
  const handleGuideStart = useCallback(
    (orientation: RulerGuide['orientation'], event: React.MouseEvent) => {
      // Left button only (D44's own rule, applied here too, S4): the middle
      // button pans and the right button opens no context menu on a ruler,
      // so neither should spawn a guide. `preventDefault` keeps a middle-
      // button press from also triggering the browser's autoscroll cursor.
      if (event.button !== 0) return;
      event.preventDefault();
      const point = stagePointFromClient(event.clientX, event.clientY);
      if (!point) return;
      const { x_mm, y_mm } = stageToMm(view, point.x, point.y);
      const position_mm = orientation === 'vertical' ? x_mm : y_mm;
      // A fresh id in case this turns out to be a placement; a move reuses
      // the axis's existing guide's own id instead (placeOrMoveGuide decides
      // which), and the drag ref below has to track WHICHEVER one it was.
      const freshId = newGuideId();
      const drag = {
        id: freshId,
        orientation,
        moved: false,
        // Spawned FROM the ruler, so the drag starts inside it (B2).
        leftRuler: false,
        downClient: { x: event.clientX, y: event.clientY },
      };
      guideDragRef.current = drag;
      setSelectedGuideId(null);
      setRulerGuides((prev) => {
        // Which guide this gesture is now dragging is decided by the state the
        // update actually runs against, not by a `rulerGuides` snapshot read
        // during render - two ruler clicks in the same tick would otherwise
        // both see "no guide yet" and the second would track an id that never
        // made it into the array. Idempotent, so StrictMode's double-invoked
        // updater is harmless.
        const existing = guideForAxis(prev, orientation);
        if (existing) drag.id = existing.id;
        return placeOrMoveGuide(prev, orientation, freshId, position_mm);
      });
    },
    [stagePointFromClient, view],
  );

  /** An EXISTING guide picked up off the canvas: the same drag, a later start. */
  const handleGuidePointerDown = useCallback(
    (guide: RulerGuide, event: { clientX: number; clientY: number }) => {
      guideDragRef.current = {
        id: guide.id,
        orientation: guide.orientation,
        moved: false,
        // Picked up from somewhere on the canvas, never from inside the
        // ruler strip itself, so this drag has already left ruler territory
        // the moment it starts (B2).
        leftRuler: true,
        downClient: { x: event.clientX, y: event.clientY },
      };
    },
    [],
  );

  // ONE pair of window listeners, always attached, no-op unless a guide is
  // being dragged (`guideDragRef`) - the drag can wander outside the ruler
  // or the Stage's own DOM bounds, which a React-level handler on either
  // would silently drop.
  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      const drag = guideDragRef.current;
      if (!drag) return;
      // The button came up somewhere outside the window - no `mouseup` here
      // to catch it (S3) - so there is no drag left to continue.
      if (event.buttons === 0) {
        guideDragRef.current = null;
        return;
      }
      if (!drag.moved) {
        // The file's own marquee-slop pattern (B2): a real click always
        // wanders a pixel or two between mousedown and mouseup, and without
        // this threshold that jitter alone flipped `moved` on tick one.
        const dx = event.clientX - drag.downClient.x;
        const dy = event.clientY - drag.downClient.y;
        if (Math.hypot(dx, dy) >= MARQUEE_SLOP_PX) drag.moved = true;
      }
      const point = stagePointFromClient(event.clientX, event.clientY);
      if (!point) return;
      // Only once the pointer has genuinely left ruler territory does a later
      // re-entry count as "dragged back onto the ruler" (B2) - see the ref's
      // own doc comment above.
      if (!guideCrossedIntoRuler(drag.orientation, point)) drag.leftRuler = true;
      const { x_mm, y_mm } = stageToMm(view, point.x, point.y);
      setRulerGuides((prev) =>
        moveGuide(prev, drag.id, drag.orientation === 'vertical' ? x_mm : y_mm),
      );
    };

    const onUp = (event: MouseEvent) => {
      const drag = guideDragRef.current;
      if (!drag) return;
      // A plain click - never past the slop, or never having left ruler
      // territory - never counts as "dragged back onto the ruler", or the
      // guide this same gesture just dropped would delete itself (B2).
      const point = stagePointFromClient(event.clientX, event.clientY);
      if (
        drag.moved &&
        drag.leftRuler &&
        point &&
        guideCrossedIntoRuler(drag.orientation, point)
      ) {
        setRulerGuides((prev) => removeGuide(prev, drag.id));
        setSelectedGuideId((id) => (id === drag.id ? null : id));
      } else if (!drag.moved) {
        // A plain click - placing/moving the axis's guide from the ruler, or
        // picking an existing one back up off the canvas without dragging it
        // anywhere - selects it (D21, AC-S8-2), the same way clicking a layer
        // selects the layer. And, the same way, it deselects whatever was
        // selected before (B4): one Delete key, one thing it can remove.
        setSelectedGuideId(drag.id);
        setSelectedIds(new Set());
      }
      guideDragRef.current = null;
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [stagePointFromClient, view]);

  /** The x chip at a guide's own ruler position was clicked (D21, AC-S8-2). */
  const handleGuideRemove = useCallback(
    (orientation: RulerGuide['orientation']) => {
      const target = guideForAxis(rulerGuides, orientation);
      if (!target) return;
      setRulerGuides((prev) => removeGuide(prev, target.id));
      setSelectedGuideId((id) => (id === target.id ? null : id));
    },
    [rulerGuides],
  );

  // Delete/Backspace removes the SELECTED guide (D21, AC-S8-2) - a second
  // removal path alongside the x chip and the drag-back gesture above. Lives
  // beside the layer keyboard shortcuts below rather than its own effect, so
  // there is one keydown listener for the whole canvas, not two racing ones.

  // -- Viewport (D33, D34) ---------------------------------------------------

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect;
      setContainerSize({ width: rect.width, height: rect.height });
    });
    observer.observe(element);
    setContainerSize({ width: element.clientWidth, height: element.clientHeight });
    return () => observer.disconnect();
  }, []);

  const handleFit = useCallback(() => {
    if (stageWidth <= 0 || stageHeight <= 0) return;
    setView(
      fitView(
        { width: stageWidth, height: stageHeight },
        { width_mm: doc.width_mm, height_mm: doc.height_mm },
      ),
    );
  }, [stageWidth, stageHeight, doc.width_mm, doc.height_mm]);

  const handleZoomReset = useCallback(() => {
    setView(
      actualSizeView(
        { width: stageWidth, height: stageHeight },
        { width_mm: doc.width_mm, height_mm: doc.height_mm },
      ),
    );
  }, [stageWidth, stageHeight, doc.width_mm, doc.height_mm]);

  // Fit once, as soon as the container has a size to fit into.
  useEffect(() => {
    if (fittedRef.current || stageWidth <= 0 || stageHeight <= 0) return;
    fittedRef.current = true;
    handleFit();
  }, [stageWidth, stageHeight, handleFit]);

  // -- Side panels (S1, D7) ---------------------------------------------------

  /**
   * `onCollapse`/`onExpand` (unlike `onResize`) fire once on MOUNT too, to
   * announce a collapsible panel's initial state - which happens before the
   * hydration effect below has replaced `panelLayout` with what is actually
   * stored, so persisting unconditionally clobbered the stored left/right/
   * railSplit with plain defaults on every load. Guarded the same way as the
   * resize handlers below, just against "has hydration run" rather than "is a
   * handle being dragged", since a collapse/expand can be a button click.
   */
  const hasHydratedRef = useRef(false);

  /**
   * True only between a handle's own `onDragging(true)` and `onDragging(false)`
   * (react-resizable-panels calls it once per pointer drag). It gates which
   * `onResize` calls are a genuine user action worth persisting.
   *
   * The library ALSO fires `onResize` on its own, outside any drag, whenever
   * the group's real pixel width first becomes known: `defaultSize` is only
   * honoured on a Panel's very first mount, and that first mount happens
   * before the group has been measured (percentages have to come from
   * SOMETHING, so a generic fallback width stands in) - once the real width
   * arrives, the panel's minSize/maxSize percentages are recomputed against
   * it and, if the mount-time percentage now reads as below the real minimum,
   * the library corrects the panel up to it and reports that as a resize.
   * Persisting that correction would floor the STORED width to the minimum
   * on every load, discarding whatever the user actually had it at - which is
   * exactly the bug this ref exists to avoid.
   */
  const draggingHandleRef = useRef(false);

  // Hydrate from localStorage after mount (avoids a hydration mismatch - see
  // the state's own comment). A stored COLLAPSED flag needs an imperative
  // `.collapse()` call here, not just the state update: the panel already
  // mounted expanded (hydration runs after mount, and `defaultSize` is only
  // ever read at mount, before this state existed), so without this the
  // collapsed half of AC-S1-5 would silently not apply on reload even though
  // the value round-trips through storage correctly.
  useEffect(() => {
    const stored = readPanelLayout();
    setPanelLayoutState(stored);
    hasHydratedRef.current = true;
    if (stored.leftCollapsed) leftPanelRef.current?.collapse();
    if (stored.rightCollapsed) rightPanelRef.current?.collapse();
  }, []);

  useEffect(() => {
    const element = panelGroupRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect;
      setPanelGroupSize({ width: rect.width, height: rect.height });
    });
    observer.observe(element);
    setPanelGroupSize({ width: element.clientWidth, height: element.clientHeight });
    return () => observer.disconnect();
  }, []);

  const persistPanelLayout = useCallback((updater: (prev: PanelLayout) => PanelLayout) => {
    setPanelLayoutState((prev) => {
      const next = updater(prev);
      writePanelLayout(next);
      return next;
    });
  }, []);

  // Percentages `react-resizable-panels` wants, converted from the persisted
  // pixel widths against the group's own measured size. Before that size is
  // known, a generic fallback keeps the first paint sane; the ResizeObserver
  // above corrects it a moment later, the same one-frame settle every other
  // measured layout in this file already accepts (`containerSize` does the
  // same at 0x0 until its own observer fires). jsdom never fires it at all
  // (no real layout engine), so this fallback is also what every panel test
  // renders against - a fixed, environment-independent number rather than 0.
  const groupWidth = panelGroupSize.width || 1200;
  const groupHeight = panelGroupSize.height || 600;
  /**
   * Below this, the side columns are `hidden` (AC-S1-7) but still mounted -
   * squeezing the group this narrow can force the library to auto-collapse a
   * panel just to satisfy its own `minSize`, which is a viewport-width
   * artefact, not a choice. `onCollapse`/`onExpand` below skip persisting
   * while the group is this narrow so a phone-width visit does not leave the
   * desktop layout collapsed the next time it is opened wide.
   */
  const isGroupInteractive = groupWidth >= 640;
  const leftPercent = (panelLayout.left / groupWidth) * 100;
  const rightPercent = (panelLayout.right / groupWidth) * 100;
  const leftMinPercent = (LEFT_MIN_PX / groupWidth) * 100;
  const leftMaxPercent = (LEFT_MAX_PX / groupWidth) * 100;
  const rightMinPercent = (RIGHT_MIN_PX / groupWidth) * 100;
  const rightMaxPercent = (RIGHT_MAX_PX / groupWidth) * 100;
  const railPercent = (panelLayout.railSplit / groupHeight) * 100;
  const railMinPercent = (RAIL_MIN_PX / groupHeight) * 100;
  const railMaxPercent = 100 - railMinPercent;

  const handleLeftResize = useCallback(
    (size: number) => {
      if (!draggingHandleRef.current) return;
      // Dragging PAST the minimum is the library's own collapse gesture, which
      // reports a run of intermediate sizes below `leftMinPercent` on its way
      // to 0 - `onCollapse` below owns that transition, so anything under the
      // real minimum is ignored here rather than clamped and persisted (that
      // would floor the stored width to LEFT_MIN_PX and lose whatever the
      // panel was actually at before the user dragged it shut).
      if (size < leftMinPercent - 0.1) return;
      persistPanelLayout((prev) => ({ ...prev, left: clampLeft((size / 100) * groupWidth) }));
    },
    [groupWidth, leftMinPercent, persistPanelLayout],
  );

  const handleRightResize = useCallback(
    (size: number) => {
      if (!draggingHandleRef.current) return;
      if (size < rightMinPercent - 0.1) return;
      persistPanelLayout((prev) => ({ ...prev, right: clampRight((size / 100) * groupWidth) }));
    },
    [groupWidth, rightMinPercent, persistPanelLayout],
  );

  const handleRailResize = useCallback(
    (size: number) => {
      if (!draggingHandleRef.current) return;
      if (size < railMinPercent - 0.1 || size > railMaxPercent + 0.1) return;
      persistPanelLayout((prev) => ({
        ...prev,
        railSplit: clampRailSplit((size / 100) * groupHeight),
      }));
    },
    [groupHeight, railMinPercent, railMaxPercent, persistPanelLayout],
  );

  // A layout change that came from actually dragging a handle is worth
  // re-centring the artboard for (unlike the collapse toggle, which the
  // chevron buttons drive directly) - the same "Fit to View" the toolbar and
  // Ctrl+0 already trigger.
  const handlePanelDragEnd = useCallback(
    (isDragging: boolean) => {
      draggingHandleRef.current = isDragging;
      if (!isDragging) handleFit();
    },
    [handleFit],
  );

  const handleZoomIn = useCallback(() => {
    setView((v) =>
      zoomAt(v, { x: stageWidth / 2, y: stageHeight / 2 }, ZOOM_BUTTON_FACTOR, ZOOM_LIMITS),
    );
  }, [stageWidth, stageHeight]);

  const handleZoomOut = useCallback(() => {
    setView((v) =>
      zoomAt(v, { x: stageWidth / 2, y: stageHeight / 2 }, 1 / ZOOM_BUTTON_FACTOR, ZOOM_LIMITS),
    );
  }, [stageWidth, stageHeight]);

  // A NATIVE wheel listener with { passive: false }: React's onWheel is passive,
  // so preventDefault there is ignored and the page scrolls instead of zooming.
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      const pointer = {
        x: event.clientX - rect.left - RULER_THICKNESS,
        y: event.clientY - rect.top - RULER_THICKNESS,
      };
      setView((v) => zoomAt(v, pointer, Math.pow(1.1, -event.deltaY / 100), ZOOM_LIMITS));
    };
    element.addEventListener('wheel', onWheel, { passive: false });
    return () => element.removeEventListener('wheel', onWheel);
  }, []);

  // -- Stage pointer handling (D35, D36) -------------------------------------

  const isBackground = useCallback((e: Konva.KonvaEventObject<MouseEvent>) => {
    const target = e.target;
    return target === target.getStage() || target.name() === 'artboard-bg';
  }, []);

  const handleStageMouseDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      const point = stageRef.current?.getPointerPosition();
      if (!point) return;
      // The middle button pans wherever it is pressed and whatever the tool is,
      // and `preventDefault` keeps the browser's autoscroll cursor away. The
      // right button starts nothing: the context menu resolves its own target.
      if (e.evt.button === 1) {
        e.evt.preventDefault();
        panRef.current = { x: point.x, y: point.y, panX: view.panX, panY: view.panY };
        setWheelPanning(true);
        return;
      }
      if (e.evt.button !== 0) return;
      if (handMode) {
        panRef.current = { x: point.x, y: point.y, panX: view.panX, panY: view.panY };
        return;
      }
      if (!isBackground(e)) return;
      const start = stageToMm(view, point.x, point.y);
      marqueeRef.current = { start, additive: e.evt.shiftKey };
      setMarquee(bandBetween(start, start));
    },
    [handMode, view, isBackground],
  );

  const handleStageMouseMove = useCallback(() => {
    const point = stageRef.current?.getPointerPosition();
    if (!point) return;
    const pan = panRef.current;
    if (pan) {
      setView((v) => ({
        ...v,
        panX: pan.panX + (point.x - pan.x),
        panY: pan.panY + (point.y - pan.y),
      }));
      return;
    }
    const band = marqueeRef.current;
    if (band) setMarquee(bandBetween(band.start, stageToMm(view, point.x, point.y)));
  }, [view]);

  const handleStageMouseUp = useCallback(() => {
    panRef.current = null;
    setWheelPanning(false);
    const band = marqueeRef.current;
    marqueeRef.current = null;
    setMarquee(null);
    if (!band) return;

    const point = stageRef.current?.getPointerPosition();
    const end = point ? stageToMm(view, point.x, point.y) : band.start;
    const rect = bandBetween(band.start, end);
    const dragged =
      rect.width_mm * scale > MARQUEE_SLOP_PX || rect.height_mm * scale > MARQUEE_SLOP_PX;

    if (!dragged) {
      // A click on empty space deselects and leaves the group (D36).
      if (!band.additive) setSelectedIds(new Set());
      setSelectedGuideId(null);
      return;
    }
    const hits = marqueeHits(layers, rect, { insideGroupId });
    setSelectedIds((prev) => (band.additive ? new Set([...prev, ...hits]) : new Set(hits)));
    setSelectedGuideId(null);
  }, [view, scale, layers, insideGroupId]);

  // A mouseup outside the canvas would otherwise leave a band or a pan running.
  useEffect(() => {
    const cancel = () => {
      panRef.current = null;
      setWheelPanning(false);
      if (marqueeRef.current) {
        marqueeRef.current = null;
        setMarquee(null);
      }
    };
    window.addEventListener('mouseup', cancel);
    return () => window.removeEventListener('mouseup', cancel);
  }, []);

  const handleStageDoubleClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (isBackground(e)) {
        setSelectedIds(new Set());
        setSelectedGuideId(null);
      }
    },
    [isBackground],
  );

  // Runs before the Radix trigger, being the deeper DOM node. It must NOT call
  // preventDefault: the trigger needs this event, and the trigger is what stops
  // the browser's own menu.
  const handleStageContextMenu = useCallback(() => {
    const point = pointerMm();
    const hitId = point ? hitLayerAt(layers, point.x_mm, point.y_mm, entered) : null;
    setMenuOnEmpty(!hitId);
    if (hitId && !selectedIds.has(hitId)) setSelectedIds(new Set([hitId]));
  }, [pointerMm, layers, entered, selectedIds]);

  // -- Undo / Redo -----------------------------------------------------------

  const handleUndo = useCallback(() => {
    const restored = history.undo();
    if (restored) {
      setLayers(restored);
      setSelectedIds(new Set());
    }
  }, [history]);

  const handleRedo = useCallback(() => {
    const restored = history.redo();
    if (restored) {
      setLayers(restored);
      setSelectedIds(new Set());
    }
  }, [history]);

  // -- Clipboard (D39) --------------------------------------------------------

  const handleCopy = useCallback(() => {
    if (selectionRoots.length === 0) return;
    const ids = new Set(selectionRoots);
    for (const rootId of selectionRoots) {
      for (const childId of descendantsOf(layers, rootId)) ids.add(childId);
    }
    setClipboard({
      layers: structuredClone(layers.filter((layer) => ids.has(layer.id))),
      roots: [...selectionRoots],
    });
  }, [layers, selectionRoots]);

  const handlePaste = useCallback(() => {
    if (!clipboard || clipboard.layers.length === 0) return;
    const cloned = cloneLayers(
      clipboard.layers,
      clipboard.roots,
      newLayerId,
      CLONE_OFFSET_MM,
      maxZ,
    );
    if (cloned.layers.length === 0) return;
    commit([...layers, ...cloned.layers], new Set(cloned.ids));
  }, [clipboard, layers, maxZ, commit]);

  const handleCut = useCallback(() => {
    handleCopy();
    deleteSelectedLayers();
  }, [handleCopy, deleteSelectedLayers]);

  // -- Visibility and lock toggles -------------------------------------------

  const handleToggleVisibility = useCallback(
    (id: string) => {
      const layer = layers.find((l) => l.id === id);
      if (layer) updateLayer(id, { visible: !layer.visible });
    },
    [layers, updateLayer],
  );

  const handleToggleLock = useCallback(
    (id: string) => {
      const layer = layers.find((l) => l.id === id);
      if (layer) updateLayer(id, { locked: !layer.locked });
    },
    [layers, updateLayer],
  );

  /**
   * A drag in the Layers panel (D43): one reorder, one history entry.
   *
   * A drop that changes nothing (into its own subtree, or onto a target that is
   * no longer there) answers the same array, and then there is nothing to undo.
   */
  const handleMoveLayer = useCallback(
    (id: string, target: ReparentTarget) => {
      const next = reparentLayer(layers, id, target);
      if (next === layers) return;
      commit(next);
    },
    [layers, commit],
  );

  const selectionLocked = useMemo(
    () =>
      selectionRoots.length > 0 &&
      selectionRoots.every((id) => layers.find((l) => l.id === id)?.locked),
    [selectionRoots, layers],
  );

  const toggleSelectionLock = useCallback(() => {
    if (selectionRoots.length === 0) return;
    const locked = !selectionLocked;
    const ids = new Set(selectionRoots);
    commit(layers.map((layer) => (ids.has(layer.id) ? { ...layer, locked } : layer)));
  }, [selectionRoots, selectionLocked, layers, commit]);

  const hideSelection = useCallback(() => {
    if (selectionRoots.length === 0) return;
    const ids = new Set(selectionRoots);
    commit(layers.map((layer) => (ids.has(layer.id) ? { ...layer, visible: false } : layer)));
  }, [selectionRoots, layers, commit]);

  // -- Keyboard shortcuts ----------------------------------------------------

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isInput =
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement;
      const modifier = e.ctrlKey || e.metaKey;

      // B/I/U/Shift+X format the selected text layer(s) whether the inline
      // editor has focus or not (AC-S2-4, D4) - checked ahead of the
      // `editingLayerId`/`isInput` guards below, because the inline editor
      // IS a textarea and would otherwise never let these through.
      if (modifier && !e.shiftKey && (e.key === 'b' || e.key === 'B')) {
        e.preventDefault();
        applyTextFormat('bold');
        return;
      }
      if (modifier && !e.shiftKey && (e.key === 'i' || e.key === 'I')) {
        e.preventDefault();
        applyTextFormat('italic');
        return;
      }
      if (modifier && !e.shiftKey && (e.key === 'u' || e.key === 'U')) {
        e.preventDefault();
        applyTextFormat('underline');
        return;
      }
      if (modifier && e.shiftKey && (e.key === 'x' || e.key === 'X')) {
        e.preventDefault();
        applyTextFormat('strikethrough');
        return;
      }

      // The inline editor is its own textarea layered over the canvas; while
      // it is open nothing else here may fire (AC-S2-8). Redundant with the
      // `isInput` check right below - which already covers it, since the
      // editor IS a textarea - kept explicit for safety per the plan.
      if (editingLayerId) return;

      if (isInput) return;

      if (e.key === ' ' && !modifier) {
        e.preventDefault();
        setSpaceHeld(true);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        selectParentGroup();
        return;
      }
      if (!modifier && (e.key === 'v' || e.key === 'V')) {
        setTool('select');
        return;
      }
      if (!modifier && (e.key === 'h' || e.key === 'H')) {
        setTool('hand');
        return;
      }
      if (modifier && e.key === '0') {
        e.preventDefault();
        handleFit();
        return;
      }
      if (modifier && e.key === '1') {
        e.preventDefault();
        handleZoomReset();
        return;
      }

      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedGuideId) {
        // The GUIDE first (B4). Selecting one already clears the layer
        // selection, so this is only ever reached with a guide selected - but
        // asking about the layers first meant that if the two ever DID overlap
        // (as they did before this), Delete silently removed the layers and
        // left the thing the user had just clicked on untouched. Cheap to make
        // the order say what is meant.
        e.preventDefault();
        setRulerGuides((prev) => removeGuide(prev, selectedGuideId));
        setSelectedGuideId(null);
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && selectedIds.size > 0) {
        e.preventDefault();
        deleteSelectedLayers();
      }
      if (e.key === 'z' && modifier && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      }
      if (e.key === 'z' && modifier && e.shiftKey) {
        e.preventDefault();
        handleRedo();
      }
      if (e.key === 'y' && modifier) {
        e.preventDefault();
        handleRedo();
      }
      if (e.key === 'd' && modifier) {
        e.preventDefault();
        duplicateSelectedLayers();
      }
      if (e.key === 'g' && modifier) {
        e.preventDefault();
        if (e.shiftKey) ungroupSelectedLayers();
        else groupSelectedLayers();
      }
      if (e.key === 'a' && modifier) {
        e.preventDefault();
        selectAll();
      }
      if (e.key === 'c' && modifier) {
        e.preventDefault();
        handleCopy();
      }
      if (e.key === 'x' && modifier) {
        e.preventDefault();
        handleCut();
      }
      if (e.key === 'v' && modifier) {
        e.preventDefault();
        handlePaste();
      }

      // Nudge with arrow keys (1mm, or 0.1mm with shift).
      const nudge = e.shiftKey ? 0.1 : 1;
      if (e.key === 'ArrowLeft' && selectedIds.size > 0) {
        e.preventDefault();
        nudgeSelection(-nudge, 0);
      }
      if (e.key === 'ArrowRight' && selectedIds.size > 0) {
        e.preventDefault();
        nudgeSelection(nudge, 0);
      }
      if (e.key === 'ArrowUp' && selectedIds.size > 0) {
        e.preventDefault();
        nudgeSelection(0, -nudge);
      }
      if (e.key === 'ArrowDown' && selectedIds.size > 0) {
        e.preventDefault();
        nudgeSelection(0, nudge);
      }
    };

    const release = (e: KeyboardEvent) => {
      if (e.key === ' ') setSpaceHeld(false);
    };

    window.addEventListener('keydown', handler);
    window.addEventListener('keyup', release);
    return () => {
      window.removeEventListener('keydown', handler);
      window.removeEventListener('keyup', release);
    };
  }, [
    selectedIds,
    selectedGuideId,
    editingLayerId,
    applyTextFormat,
    deleteSelectedLayers,
    duplicateSelectedLayers,
    groupSelectedLayers,
    ungroupSelectedLayers,
    selectParentGroup,
    selectAll,
    handleUndo,
    handleRedo,
    handleCopy,
    handleCut,
    handlePaste,
    handleFit,
    handleZoomReset,
    nudgeSelection,
  ]);

  // A window that loses focus while Space is down would otherwise stay in hand.
  useEffect(() => {
    const clear = () => setSpaceHeld(false);
    window.addEventListener('blur', clear);
    return () => window.removeEventListener('blur', clear);
  }, []);

  // -- Expose current doc for save ------------------------------------------

  /** Call onChange with the current layers state. */
  const save = useCallback(() => {
    onChange({ ...doc, layers });
  }, [doc, layers, onChange]);

  // A host that owns the document (the request designer) hears every change, so
  // switching to another line does not throw the edits away. The template
  // editor passes nothing and keeps its Save-only behaviour.
  useEffect(() => {
    onLayersChange?.(layers);
  }, [layers, onLayersChange]);

  // -- Derived state for toolbar ---------------------------------------------

  const selectedLayer = useMemo(() => {
    if (selectedIds.size === 1) {
      const id = Array.from(selectedIds)[0];
      return layers.find((l) => l.id === id) ?? null;
    }
    return null;
  }, [selectedIds, layers]);

  const selectionIsGroup = selectedLayer?.props.kind === 'group';

  const selectedData = selectedLayer ? dataOf(selectedLayer) : null;

  /** What the inspector's Content box falls back to when nothing was typed. */
  const selectedResolvedText = selectedLayer
    ? resolveSlotText(selectedLayer, selectedData)
    : null;

  /**
   * The content the Insert field dialog opens on, and where Done writes it.
   *
   * The same rule the Inspector's Content box already follows: a slot-bound
   * layer is edited through `text_override` so the binding survives, an unbound
   * one through its own text. Each path is one `setLayers` and one history
   * entry, so a whole dialog's worth of edits undoes in one step.
   */
  const selectedContent = selectedLayer
    ? selectedLayer.slot_binding
      ? selectedLayer.text_override ??
        selectedResolvedText ??
        (selectedLayer.props.kind === 'text' ? selectedLayer.props.text : '')
      : selectedLayer.props.kind === 'text'
        ? selectedLayer.props.text
        : ''
    : '';

  const writeSelectedContent = useCallback(
    (content: string) => {
      if (!selectedLayer) return;
      if (selectedLayer.slot_binding) {
        updateLayer(selectedLayer.id, { text_override: content });
      } else if (selectedLayer.props.kind === 'text') {
        updateLayerProps(selectedLayer.id, { ...selectedLayer.props, text: content });
      }
    },
    [selectedLayer, updateLayer, updateLayerProps],
  );

  /**
   * The inline editor's commit (S2, D5): the exact same rule
   * `writeSelectedContent` follows, plus closing the editor. `editingLayerId`
   * is always the sole selected id while the editor is open (set together in
   * `handleLayerDoubleClick`), so `writeSelectedContent` targets the right
   * layer.
   */
  const commitInlineEdit = useCallback(
    (content: string) => {
      writeSelectedContent(content);
      setEditingLayerId(null);
    },
    [writeSelectedContent],
  );

  // Belt-and-braces: if the layer being edited stops being the sole
  // selection (or the selection stops being that text layer) through some
  // path other than the editor's own commit, close it rather than leaving it
  // open on a stale layer.
  useEffect(() => {
    if (!editingLayerId) return;
    if (!selectedLayer || selectedLayer.id !== editingLayerId || selectedLayer.props.kind !== 'text') {
      setEditingLayerId(null);
    }
  }, [editingLayerId, selectedLayer]);

  /** The bound thing, named the way a person recognises it. Never a UUID. */
  const selectedBindingLabel = describeBindingData(selectedData);

  /** What each previewed block is showing, named for a person (D53). */
  const previewChoices = useMemo(() => {
    const out: Record<string, PreviewChoice> = {};
    for (const [groupId, binding] of Object.entries(previews)) {
      const id = binding.product_id ?? binding.product_set_id;
      const label = describeBindingData(bindings.get(binding));
      if (id && label) out[groupId] = { id, label };
    }
    return out;
  }, [previews, bindings]);

  /**
   * The block the selection sits in, so the Inspector - and the on-canvas eye
   * chip below - can preview THAT block. A child answers for its block:
   * somebody who clicked the code text wants the whole block's product, not
   * a binding on one text layer.
   */
  const selectedBlock = selectedLayer
    ? previewBlockOf(selectedLayer, previewBlocks, groupOfChild)
    : null;

  /** The block the pointer is hovering, if any (D10, S6). */
  const hoveredBlock = useMemo(() => {
    if (!hoveredLayerId) return null;
    const layer = layers.find((l) => l.id === hoveredLayerId);
    return layer ? previewBlockOf(layer, previewBlocks, groupOfChild) : null;
  }, [hoveredLayerId, layers, previewBlocks, groupOfChild]);

  /**
   * Which block's on-canvas eye is showing right now: hovered, then the
   * chip's OWN hover (B1 - keeps it mounted once the pointer has crossed
   * onto it, even after the block's own hover cleared), then selected.
   */
  const activeCanvasEyeBlockId =
    hoveredBlock?.groupId ?? chipHoveredBlockId ?? selectedBlock?.groupId ?? null;

  /** The bound product's photos, for the image picker's first tab. */
  const pickerProductImages = useMemo(() => {
    if (!imagePicker) return [];
    const layer = layers.find((l) => l.id === imagePicker.layerId);
    const data = layer ? dataOf(layer) : null;
    return data?.kind === 'product' ? data.product.images : [];
  }, [imagePicker, layers, dataOf]);

  // -- Render ----------------------------------------------------------------

  /**
   * The whole-tag eye's on-canvas position (S5). Anchored to the frame's own
   * top-right corner, but CLAMPED into the viewport: a pan or zoom that
   * carries that corner above the ruler or off either side must not bury the
   * one control that reaches the whole-tag preview.
   */
  const wholeTagEyePosition = useMemo(() => {
    const rawLeft = RULER_THICKNESS + view.panX + canvasWidthPx - 28;
    const rawTop = RULER_THICKNESS + view.panY - 28;
    const maxLeft = Math.max(RULER_THICKNESS + 2, containerSize.width - 26);
    return {
      left: Math.min(Math.max(rawLeft, RULER_THICKNESS + 2), maxLeft),
      top: Math.max(rawTop, RULER_THICKNESS + 2),
    };
  }, [view.panX, view.panY, canvasWidthPx, containerSize.width]);

  const sortedLayers = useMemo(
    () => [...layers].sort((a, b) => a.z_index - b.z_index),
    [layers],
  );

  const hasSelection = selectedIds.size > 0;
  const canEnterGroup = selectionIsGroup;
  const canSelectParent = insideGroupId !== null;

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <CanvasToolbar
        tool={tool}
        onToolChange={setTool}
        onAddText={handleAddText}
        onAddShape={handleAddShape}
        onAddImage={handleAddImage}
        onAddProductSlot={handleAddProductSlot}
        onAddPriceBadge={handleAddPriceBadge}
        onAddBadge={handleAddBadge}
        onAddBarcode={handleAddBarcode}
        onAddProduct={() => setPicker({ kind: 'add-product' })}
        onAddSet={() => setPicker({ kind: 'add-set' })}
        onAddAlternativesRow={() => setPicker({ kind: 'alternatives' })}
        onAddAccessoriesStrip={() => setPicker({ kind: 'accessories' })}
        onUndo={handleUndo}
        onRedo={handleRedo}
        canUndo={history.canUndo}
        canRedo={history.canRedo}
        zoom={view.zoom}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onZoomReset={handleZoomReset}
        onFit={handleFit}
        onDeleteSelected={deleteSelectedLayers}
        onDuplicateSelected={duplicateSelectedLayers}
        onGroupSelected={groupSelectedLayers}
        onUngroupSelected={ungroupSelectedLayers}
        hasSelection={hasSelection}
        hasMultiSelection={selectedIds.size >= 2}
        selectionIsGroup={selectionIsGroup}
      />

      <div ref={panelGroupRef} className="flex flex-1 overflow-hidden">
        {/* Left column collapsed strip: rendered OUTSIDE the panel so it stays
            clickable while the panel itself is at collapsedSize={0}. */}
        {panelLayout.leftCollapsed && (
          <button
            type="button"
            className="hidden w-6 shrink-0 items-start justify-center border-r bg-muted/30 pt-2 hover:bg-muted md:flex"
            title="Expand Lines + Layers"
            aria-label="Expand Lines + Layers"
            onClick={() => {
              leftPanelRef.current?.expand(leftPercent);
              handleFit();
            }}
          >
            <ChevronRight className="size-3.5" />
          </button>
        )}

        <ResizablePanelGroup direction="horizontal" className="flex-1">
          {/* Left sidebar: the host's rail, then the Layers panel (AC-S1-1, AC-S1-3). */}
          <ResizablePanel
            ref={leftPanelRef}
            id="canvas-left"
            order={1}
            collapsible
            collapsedSize={0}
            minSize={leftMinPercent}
            maxSize={leftMaxPercent}
            defaultSize={panelLayout.leftCollapsed ? 0 : leftPercent}
            onResize={handleLeftResize}
            onCollapse={() => {
              if (!hasHydratedRef.current || !isGroupInteractive) return;
              persistPanelLayout((prev) => ({ ...prev, leftCollapsed: true }));
            }}
            onExpand={() => {
              if (!hasHydratedRef.current || !isGroupInteractive) return;
              persistPanelLayout((prev) => ({ ...prev, leftCollapsed: false }));
            }}
            className="relative hidden md:flex md:flex-col md:overflow-hidden"
          >
            <button
              type="button"
              className="absolute right-1 top-1 z-10 flex size-5 items-center justify-center rounded bg-background/80 text-muted-foreground hover:bg-accent hover:text-foreground"
              title="Collapse Lines + Layers"
              aria-label="Collapse Lines + Layers"
              onClick={() => {
                leftPanelRef.current?.collapse();
                handleFit();
              }}
            >
              <ChevronLeft className="size-3.5" />
            </button>
            {leftRail ? (
              <ResizablePanelGroup direction="vertical" className="h-full">
                <ResizablePanel
                  id="canvas-left-rail"
                  order={1}
                  minSize={railMinPercent}
                  maxSize={railMaxPercent}
                  defaultSize={railPercent}
                  onResize={handleRailResize}
                  className="flex flex-col"
                >
                  {/* The Panel itself clips at its own bounds (overflow:hidden
                      from the primitive) - this inner div is what actually
                      scrolls once the divider drags the pane below the rail's
                      natural content height. */}
                  <div className="flex h-full flex-col overflow-y-auto">{leftRail}</div>
                </ResizablePanel>
                <ResizableHandle
                  withHandle
                  onDragging={handlePanelDragEnd}
                  aria-label="Resize Lines and Layers"
                />
                <ResizablePanel id="canvas-left-layers" order={2} minSize={railMinPercent} className="min-h-0">
                  <LayersPanel
                    layers={layers}
                    selectedIds={selectedIds}
                    onSelect={handleSelect}
                    onToggleVisibility={handleToggleVisibility}
                    onToggleLock={handleToggleLock}
                    onMoveLayer={handleMoveLayer}
                  />
                </ResizablePanel>
              </ResizablePanelGroup>
            ) : (
              <div className="min-h-0 flex-1">
                <LayersPanel
                  layers={layers}
                  selectedIds={selectedIds}
                  onSelect={handleSelect}
                  onToggleVisibility={handleToggleVisibility}
                  onToggleLock={handleToggleLock}
                  onMoveLayer={handleMoveLayer}
                />
              </div>
            )}
          </ResizablePanel>
          <ResizableHandle
            withHandle
            className="hidden md:flex"
            onDragging={handlePanelDragEnd}
            aria-label="Resize Lines and Layers panel"
          />

          {/* Centre: canvas workspace. The Stage fills it and the artboard sits at
              a pan offset inside (D33), so there is nothing to scroll. */}
          <ResizablePanel id="canvas-centre" order={2} className="flex">
        <ContextMenu>
          <ContextMenuTrigger asChild>
            <div
              ref={containerRef}
              className={cn(
                'relative flex-1 overflow-hidden bg-muted/50',
                handMode && 'cursor-grab active:cursor-grabbing',
                wheelPanning && 'cursor-grabbing',
              )}
            >
              <CanvasRulers
                widthMm={doc.width_mm}
                heightMm={doc.height_mm}
                scale={scale}
                originX={view.panX}
                originY={view.panY}
                viewportWidth={stageWidth}
                viewportHeight={stageHeight}
                onGuideStart={handleGuideStart}
                verticalGuideMm={verticalGuide?.position_mm ?? null}
                horizontalGuideMm={horizontalGuide?.position_mm ?? null}
                onGuideRemove={handleGuideRemove}
              />

              <div
                className="absolute"
                style={{ left: RULER_THICKNESS, top: RULER_THICKNESS }}
              >
                <Stage
                  ref={stageRef as React.RefObject<Konva.Stage>}
                  width={stageWidth}
                  height={stageHeight}
                  onMouseDown={handleStageMouseDown}
                  onMouseMove={handleStageMouseMove}
                  onMouseUp={handleStageMouseUp}
                  onDblClick={handleStageDoubleClick}
                  onContextMenu={handleStageContextMenu}
                >
                  <KonvaLayer x={view.panX} y={view.panY}>
                    {/* White tag background */}
                    <Rect
                      name="artboard-bg"
                      x={0}
                      y={0}
                      width={canvasWidthPx}
                      height={canvasHeightPx}
                      fill="#ffffff"
                      stroke="#d4d4d8"
                      strokeWidth={1}
                    />

                    {/* Layers, clipped to the artboard (S9 review S4): a
                        layer dragged or resized past the tag's own edge is
                        hidden on screen exactly the way TagSheetRenderer's
                        `overflow: hidden` clips it on the printed sheet -
                        WYSIWYG after a shrink, not a canvas that still shows
                        what the PDF will not. */}
                    <Group
                      clipFunc={(ctx) => {
                        ctx.rect(0, 0, canvasWidthPx, canvasHeightPx);
                      }}
                    >
                      {sortedLayers.map((layer) => (
                        <KonvaTagLayer
                          key={layer.id}
                          layer={layer}
                          scale={scale}
                          display={layerDisplay(layer, dataOf(layer), library.assetUrls)}
                          draggable={!handMode}
                          listening={
                            !handMode &&
                            !(layer.props.kind === 'group' && entered.has(layer.id))
                          }
                          onSelect={handleCanvasSelect}
                          onDoubleClick={handleLayerDoubleClick}
                          onDragStart={handleDragStart}
                          onDragMove={handleDragMove}
                          onDragEnd={handleDragEnd}
                          onHoverChange={handleLayerHoverChange}
                        />
                      ))}
                    </Group>

                    {/* Snap guides */}
                    {guides.map((g, i) =>
                      g.orientation === 'vertical' ? (
                        <Line
                          key={`guide-v-${i}`}
                          points={[
                            g.position_mm * scale,
                            0,
                            g.position_mm * scale,
                            canvasHeightPx,
                          ]}
                          stroke="#f43f5e"
                          strokeWidth={0.5}
                          dash={[4, 4]}
                          listening={false}
                        />
                      ) : (
                        <Line
                          key={`guide-h-${i}`}
                          points={[
                            0,
                            g.position_mm * scale,
                            canvasWidthPx,
                            g.position_mm * scale,
                          ]}
                          stroke="#f43f5e"
                          strokeWidth={0.5}
                          dash={[4, 4]}
                          listening={false}
                        />
                      ),
                    )}

                    {/* Ruler guides (D9/D17, S6; D21 - one per axis, S8).
                        Dotted, and a different colour from the transient
                        snap guides above so the two are never confused -
                        these are placed on purpose and stay until removed.
                        `listening={!handMode}` (S2) so the hand tool can pan
                        through them like everything else, and a narrower
                        `hitStrokeWidth` so a guide crossing a layer does not
                        turn a whole strip of that layer unselectable. A
                        SELECTED guide (D21, AC-S8-2) draws solid and thicker
                        instead of dashed, so Delete/Backspace has a visible
                        target to confirm against. */}
                    {rulerGuides.map((g) =>
                      g.orientation === 'vertical' ? (
                        <Line
                          key={g.id}
                          points={[g.position_mm * scale, 0, g.position_mm * scale, canvasHeightPx]}
                          stroke="#0ea5e9"
                          strokeWidth={g.id === selectedGuideId ? 2 : 1}
                          dash={g.id === selectedGuideId ? undefined : [2, 3]}
                          listening={!handMode}
                          hitStrokeWidth={4}
                          onMouseDown={(e) => {
                            e.cancelBubble = true;
                            handleGuidePointerDown(g, e.evt);
                          }}
                        />
                      ) : (
                        <Line
                          key={g.id}
                          points={[0, g.position_mm * scale, canvasWidthPx, g.position_mm * scale]}
                          stroke="#0ea5e9"
                          strokeWidth={g.id === selectedGuideId ? 2 : 1}
                          dash={g.id === selectedGuideId ? undefined : [2, 3]}
                          listening={!handMode}
                          hitStrokeWidth={4}
                          onMouseDown={(e) => {
                            e.cancelBubble = true;
                            handleGuidePointerDown(g, e.evt);
                          }}
                        />
                      ),
                    )}

                    {/* ONE Transformer, after every layer, for the selection. */}
                    <Transformer
                      ref={transformerRef}
                      rotateEnabled
                      keepRatio={false}
                      listening={!handMode}
                      onTransform={handleTransform}
                      onTransformEnd={handleTransformEnd}
                      enabledAnchors={[
                        'top-left',
                        'top-right',
                        'bottom-left',
                        'bottom-right',
                        'middle-left',
                        'middle-right',
                        'top-center',
                        'bottom-center',
                      ]}
                      boundBoxFunc={(_oldBox, newBox) => {
                        // Minimum size = 2mm in pixels.
                        const minSize = 2 * scale;
                        if (newBox.width < minSize || newBox.height < minSize) {
                          return {
                            ...newBox,
                            width: Math.max(newBox.width, minSize),
                            height: Math.max(newBox.height, minSize),
                          };
                        }
                        return newBox;
                      }}
                    />

                    {/* Marquee band */}
                    {marquee && (
                      <Rect
                        x={marquee.x_mm * scale}
                        y={marquee.y_mm * scale}
                        width={marquee.width_mm * scale}
                        height={marquee.height_mm * scale}
                        fill="#3b82f6"
                        opacity={0.12}
                        stroke="#3b82f6"
                        strokeWidth={1}
                        listening={false}
                      />
                    )}
                  </KonvaLayer>
                </Stage>
              </div>

              {/* Per-block preview eyes (D10, S6): hover or select a
                  previewable block to reveal its eye, right on the block. */}
              {previewBlocks.map((block) => {
                if (activeCanvasEyeBlockId !== block.groupId) return null;
                const layer = layers.find((l) => l.id === block.groupId);
                if (!layer) return null;
                return (
                  <PreviewEyeButton
                    key={block.groupId}
                    label={
                      previewChoices[block.groupId]
                        ? `Previewing ${previewChoices[block.groupId].label}`
                        : `Preview ${block.label}`
                    }
                    active={Boolean(previewChoices[block.groupId])}
                    style={{
                      left:
                        RULER_THICKNESS +
                        view.panX +
                        (layer.x_mm + layer.width_mm) * scale -
                        24,
                      top: RULER_THICKNESS + view.panY + layer.y_mm * scale + 4,
                    }}
                    onClick={() => openBlockPreview(block.groupId)}
                    onMouseEnter={() => handleChipHoverChange(block.groupId, true)}
                    onMouseLeave={() => handleChipHoverChange(block.groupId, false)}
                  />
                );
              })}

              {/* The whole-tag eye, on the frame itself (D10, AC-S6-5): one
                  product choice resolves every loose bound layer at once.
                  Always visible when eligible, unlike a block's own eye -
                  there is no single layer on the tag to hover for it.
                  Clamped into the viewport (S5) so a pan or zoom that carries
                  the frame's own corner off-screen cannot bury it. */}
              {wholeTagPreviewBlock && (
                <>
                  <PreviewEyeButton
                    label={
                      previewChoices[WHOLE_TAG_BLOCK_ID]
                        ? `Previewing ${previewChoices[WHOLE_TAG_BLOCK_ID].label}`
                        : 'Preview the whole tag'
                    }
                    active={Boolean(previewChoices[WHOLE_TAG_BLOCK_ID])}
                    style={wholeTagEyePosition}
                    onClick={() => openBlockPreview(WHOLE_TAG_BLOCK_ID)}
                  />
                  {/* Clear affordance (S1), mirroring PreviewBlockInspector's
                      own X: a whole-tag preview is otherwise only clearable
                      from the Inspector, which is not on screen for whatever
                      layer is currently selected. */}
                  {previewChoices[WHOLE_TAG_BLOCK_ID] && (
                    <button
                      type="button"
                      className="absolute z-20 flex h-3.5 w-3.5 items-center justify-center rounded-full border bg-background text-muted-foreground shadow-sm hover:bg-accent hover:text-foreground"
                      style={{
                        left: wholeTagEyePosition.left - 6,
                        top: wholeTagEyePosition.top - 6,
                      }}
                      title="Stop previewing the whole tag"
                      aria-label="Stop previewing the whole tag"
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => {
                        e.stopPropagation();
                        clearBlockPreview(WHOLE_TAG_BLOCK_ID);
                      }}
                    >
                      <X className="size-2" />
                    </button>
                  )}
                </>
              )}

              {/* Inline text edit (S2, D5): a plain textarea laid over the
                  node, same maths `KonvaTagLayer` uses for the node itself. */}
              {editingLayerId &&
                selectedLayer &&
                selectedLayer.id === editingLayerId &&
                selectedLayer.props.kind === 'text' && (
                  <InlineTextEditor
                    key={selectedLayer.id}
                    layer={selectedLayer}
                    value={selectedContent}
                    scale={scale}
                    originX={RULER_THICKNESS + view.panX}
                    originY={RULER_THICKNESS + view.panY}
                    onCommit={commitInlineEdit}
                  />
                )}
            </div>
          </ContextMenuTrigger>

          <ContextMenuContent className="w-56">
            {hasSelection && !menuOnEmpty ? (
              <>
                <ContextMenuItem onSelect={handleCut}>
                  <Scissors />
                  Cut
                  <ContextMenuShortcut>Ctrl+X</ContextMenuShortcut>
                </ContextMenuItem>
                <ContextMenuItem onSelect={handleCopy}>
                  <Copy />
                  Copy
                  <ContextMenuShortcut>Ctrl+C</ContextMenuShortcut>
                </ContextMenuItem>
                <ContextMenuItem onSelect={handlePaste} disabled={!clipboard}>
                  <ClipboardPaste />
                  Paste
                  <ContextMenuShortcut>Ctrl+V</ContextMenuShortcut>
                </ContextMenuItem>
                <ContextMenuItem onSelect={duplicateSelectedLayers}>
                  <Copy />
                  Duplicate
                  <ContextMenuShortcut>Ctrl+D</ContextMenuShortcut>
                </ContextMenuItem>

                <ContextMenuSeparator />

                <ContextMenuItem onSelect={() => reorderSelection('front')}>
                  <ArrowUpToLine />
                  Bring to Front
                </ContextMenuItem>
                <ContextMenuItem onSelect={() => reorderSelection('forward')}>
                  <ArrowUp />
                  Bring Forward
                </ContextMenuItem>
                <ContextMenuItem onSelect={() => reorderSelection('backward')}>
                  <ArrowDown />
                  Send Backward
                </ContextMenuItem>
                <ContextMenuItem onSelect={() => reorderSelection('back')}>
                  <ArrowDownToLine />
                  Send to Back
                </ContextMenuItem>

                <ContextMenuSeparator />

                {selectionIsGroup ? (
                  <ContextMenuItem onSelect={ungroupSelectedLayers}>
                    <Ungroup />
                    Ungroup
                  </ContextMenuItem>
                ) : (
                  <ContextMenuItem
                    onSelect={groupSelectedLayers}
                    disabled={selectionRoots.length < 2}
                  >
                    <GroupIcon />
                    Group
                    <ContextMenuShortcut>Ctrl+G</ContextMenuShortcut>
                  </ContextMenuItem>
                )}
                {canEnterGroup && (
                  <ContextMenuItem onSelect={enterSelectedGroup}>
                    <CornerRightDown />
                    Enter Group
                  </ContextMenuItem>
                )}
                {canSelectParent && (
                  <ContextMenuItem onSelect={selectParentGroup}>
                    <CornerLeftUp />
                    Select Parent Group
                    <ContextMenuShortcut>Esc</ContextMenuShortcut>
                  </ContextMenuItem>
                )}

                <ContextMenuSeparator />

                <ContextMenuItem onSelect={toggleSelectionLock}>
                  {selectionLocked ? <Unlock /> : <Lock />}
                  {selectionLocked ? 'Unlock' : 'Lock'}
                </ContextMenuItem>
                <ContextMenuItem onSelect={hideSelection}>
                  <EyeOff />
                  Hide
                </ContextMenuItem>

                <ContextMenuSeparator />

                <ContextMenuItem variant="destructive" onSelect={deleteSelectedLayers}>
                  <Trash2 />
                  Delete
                  <ContextMenuShortcut>Del</ContextMenuShortcut>
                </ContextMenuItem>
              </>
            ) : (
              <>
                <ContextMenuItem onSelect={handlePaste} disabled={!clipboard}>
                  <ClipboardPaste />
                  Paste
                  <ContextMenuShortcut>Ctrl+V</ContextMenuShortcut>
                </ContextMenuItem>
                <ContextMenuItem onSelect={selectAll}>
                  <SquareDashed />
                  Select All
                  <ContextMenuShortcut>Ctrl+A</ContextMenuShortcut>
                </ContextMenuItem>
                <ContextMenuSeparator />
                <ContextMenuItem onSelect={handleFit}>
                  <Expand />
                  Fit to View
                  <ContextMenuShortcut>Ctrl+0</ContextMenuShortcut>
                </ContextMenuItem>
                <ContextMenuItem onSelect={handleZoomReset}>
                  <Percent />
                  Zoom 100%
                  <ContextMenuShortcut>Ctrl+1</ContextMenuShortcut>
                </ContextMenuItem>
              </>
            )}
          </ContextMenuContent>
        </ContextMenu>
          </ResizablePanel>

          {/* Right sidebar: Inspector panel (AC-S1-2, AC-S1-3). */}
          <ResizableHandle
            withHandle
            className="hidden lg:flex"
            onDragging={handlePanelDragEnd}
            aria-label="Resize Inspector panel"
          />
          <ResizablePanel
            ref={rightPanelRef}
            id="canvas-right"
            order={3}
            collapsible
            collapsedSize={0}
            minSize={rightMinPercent}
            maxSize={rightMaxPercent}
            defaultSize={panelLayout.rightCollapsed ? 0 : rightPercent}
            onResize={handleRightResize}
            onCollapse={() => {
              if (!hasHydratedRef.current || !isGroupInteractive) return;
              persistPanelLayout((prev) => ({ ...prev, rightCollapsed: true }));
            }}
            onExpand={() => {
              if (!hasHydratedRef.current || !isGroupInteractive) return;
              persistPanelLayout((prev) => ({ ...prev, rightCollapsed: false }));
            }}
            className="relative hidden lg:block"
          >
            <button
              type="button"
              className="absolute right-1 top-1 z-10 flex size-5 items-center justify-center rounded bg-background/80 text-muted-foreground hover:bg-accent hover:text-foreground"
              title="Collapse Inspector"
              aria-label="Collapse Inspector"
              onClick={() => {
                rightPanelRef.current?.collapse();
                handleFit();
              }}
            >
              <ChevronRight className="size-3.5" />
            </button>
            <InspectorPanel
              layer={selectedLayer}
              onUpdate={updateLayer}
              onUpdateProps={updateLayerProps}
              resolvedText={selectedResolvedText}
              bindingLabel={selectedBindingLabel}
              fontOptions={library.fontOptions}
              onUploadFont={() => setFontUploadOpen(true)}
              onInsertField={() => setInsertFieldOpen(true)}
              onChooseImage={handleChooseImage}
              onChooseBadge={handleChooseBadge}
              onRebind={handleRebind}
              onRelinkGroup={handleRelinkGroup}
              onUseTemplate={onUseTemplate}
              previewBlockId={selectedBlock?.groupId ?? null}
              previewBlockLabel={
                selectedBlock ? previewChoices[selectedBlock.groupId]?.label ?? null : null
              }
              onPreviewBlock={openBlockPreview}
              onClearBlockPreview={clearBlockPreview}
            />
          </ResizablePanel>
        </ResizablePanelGroup>

        {/* Right column collapsed strip - see the left column's own comment. */}
        {panelLayout.rightCollapsed && (
          <button
            type="button"
            className="hidden w-6 shrink-0 items-start justify-center border-l bg-muted/30 pt-2 hover:bg-muted lg:flex"
            title="Expand Inspector"
            aria-label="Expand Inspector"
            onClick={() => {
              rightPanelRef.current?.expand(rightPercent);
              handleFit();
            }}
          >
            <ChevronLeft className="size-3.5" />
          </button>
        )}
      </div>

      {/* Pickers. Rendered here rather than beside their buttons so the
          canvas keeps its selection while a dialog is open. */}
      <ProductPickDialog
        open={picker.kind !== 'none'}
        mode={
          picker.kind === 'add-set'
            ? 'set'
            : picker.kind === 'rebind'
              ? picker.mode
              : picker.kind === 'preview'
                ? picker.mode
                : 'product'
        }
        multiple={picker.kind === 'alternatives' || picker.kind === 'accessories'}
        title={
          picker.kind === 'add-set'
            ? 'Add a product set'
            : picker.kind === 'rebind'
              ? 'Change what this block is about'
              : picker.kind === 'preview'
                ? picker.groupId === WHOLE_TAG_BLOCK_ID
                  ? 'Preview the whole tag with'
                  : 'Preview this block with'
                : picker.kind === 'alternatives'
                  ? 'Add an alternatives row'
                  : picker.kind === 'accessories'
                    ? 'Add an accessories strip'
                    : 'Add a product'
        }
        confirmLabel={
          picker.kind === 'rebind'
            ? 'Rebind'
            : picker.kind === 'preview'
              ? 'Preview'
              : 'Add'
        }
        busy={pickerBusy}
        onCancel={closePicker}
        onConfirm={(ids) => {
          void handlePick(ids);
        }}
      />

      <AssetPickerDialog
        open={imagePicker !== null}
        productImages={pickerProductImages}
        allowProductPhotos={!imagePicker?.badge}
        uploadKind={imagePicker?.badge ? 'badge' : 'decorative'}
        title={imagePicker?.badge ? 'Choose a badge' : 'Choose an image'}
        onCancel={() => setImagePicker(null)}
        onPick={handleImagePicked}
      />

      <InsertFieldDialog
        open={insertFieldOpen}
        value={selectedContent}
        data={selectedData ?? null}
        specKeys={library.specKeys}
        onCancel={() => setInsertFieldOpen(false)}
        onDone={(content) => {
          setInsertFieldOpen(false);
          writeSelectedContent(content);
        }}
      />

      <FontUploadDialog
        open={fontUploadOpen}
        onCancel={() => setFontUploadOpen(false)}
        onUploaded={(asset) => {
          library.remember(asset);
          setFontUploadOpen(false);
        }}
      />

      {/* Save bar (sticky bottom). Absent when the host owns saving. */}
      <div
        className={cn(
          'flex h-10 shrink-0 items-center justify-end gap-2 border-t bg-background px-4',
          hideSaveBar && 'hidden',
        )}
      >
        <span className="text-xs text-muted-foreground">
          {layers.length} layer{layers.length !== 1 ? 's' : ''}
          {' / '}
          {doc.width_mm} x {doc.height_mm} mm
        </span>
        <button
          type="button"
          className="rounded bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          onClick={save}
        >
          Save
        </button>
      </div>
    </div>
  );
}

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
  defaultPriceFieldProps,
  defaultPriceBadgeProps,
  defaultBadgeProps,
} from '@/lib/dealer-kit/tag-template-types';
import {
  buildAccessoriesStrip,
  buildAlternativesRow,
  buildProductBlock,
  buildSetBlock,
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
} from 'lucide-react';
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
import { useCanvasHistory } from './useCanvasHistory';
import { useSnapGuides } from './useSnapGuides';

// This component is loaded with ssr:false by the page, so direct imports are safe.
import { Stage, Layer as KonvaLayer, Rect, Line, Transformer } from 'react-konva';
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
  | { kind: 'preview' };

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
  const [view, setView] = useState<CanvasView>({ zoom: 1, panX: 0, panY: 0 });
  const [tool, setTool] = useState<CanvasTool>('select');
  const [spaceHeld, setSpaceHeld] = useState(false);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
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
  /** True while the middle button is held: the hand tool, borrowed (D44). */
  const [wheelPanning, setWheelPanning] = useState(false);
  /**
   * The product the canvas is DRAWN against while previewing (D41).
   *
   * Editor state only. It is never written into `layers` and Save never sees
   * it, which is the whole point: a template ships unbound so it can be reused
   * for any product in its family, and looking at it with real data must not
   * quietly bind it.
   */
  const [preview, setPreview] = useState<GroupBinding | null>(null);

  const bindings = useTagBindings(promotionId);
  const library = useKitLibrary();

  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage | null>(null);
  const transformerRef = useRef<Konva.Transformer>(null);
  const dragRef = useRef<DragSession | null>(null);
  const panRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const marqueeRef = useRef<{
    start: { x_mm: number; y_mm: number };
    additive: boolean;
  } | null>(null);
  const fittedRef = useRef(false);

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
      // While previewing, EVERY layer resolves against the preview (D41): a
      // template ships unbound on purpose, so consulting the group first would
      // leave every slot empty and there would be nothing to look at.
      if (preview) return preview;
      if (layer.props.kind === 'group') return layer.props.binding;
      const group = groupOfChild.get(layer.id);
      return group && group.props.kind === 'group' ? group.props.binding : undefined;
    },
    [groupOfChild, preview],
  );

  const dataOf = useCallback(
    (layer: TagLayer) => {
      // The host already knows what this canvas is about (D51), so nothing has
      // to be looked up per layer. A preview still wins: it is the deliberate
      // "show me this other thing" and the host's data is the default.
      if (!preview && boundData) return boundData;
      return bindings.get(bindingOf(layer));
    },
    [bindings, bindingOf, preview, boundData],
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

  const handleAddPriceField = useCallback(() => {
    addLayer({
      ...makeBaseLayer('price_field', 40, 15),
      props: defaultPriceFieldProps(),
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

  // -- Bound blocks (D27) and preview (D41) ----------------------------------

  const closePicker = useCallback(() => {
    setPicker({ kind: 'none' });
    setPickerBusy(false);
  }, []);

  /**
   * Whether the template is about a SET rather than a product.
   *
   * Read off the layers rather than off a binding, because a template carries
   * no binding: a `set_members` slot is the document saying what it is for.
   */
  const previewMode: PickMode = useMemo(
    () => (layers.some((layer) => layer.slot_binding === 'set_members') ? 'set' : 'product'),
    [layers],
  );

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
          const isSet = previewMode === 'set';
          const loaded = isSet
            ? await bindings.loadSet(ids[0])
            : await bindings.loadProduct(ids[0]);
          if (!loaded) return;
          setPreview(isSet ? { product_set_id: ids[0] } : { product_id: ids[0] });
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
      previewMode,
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
          childIds.has(layer.id) && layer.slot_binding
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

  const handleLayerDoubleClick = useCallback(
    (rawId: string) => {
      const targetId = resolveTarget(rawId);
      const target = layers.find((layer) => layer.id === targetId);
      if (!target || target.props.kind !== 'group') return;
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
    [layers, computeSnap, doc.width_mm, doc.height_mm, scale],
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

  const handleTransformEnd = useCallback(() => {
    const transformer = transformerRef.current;
    if (!transformer) return;

    // Read and reset the Konva scale BEFORE touching state: a React updater can
    // run twice, and a second read would see the already-reset scale and undo
    // the resize.
    const changes = transformer.nodes().map((node) => {
      const scaleX = node.scaleX();
      const scaleY = node.scaleY();
      node.scaleX(1);
      node.scaleY(1);
      return {
        id: node.id(),
        attrs: {
          x_mm: node.x() / scale,
          y_mm: node.y() / scale,
          width_mm: (node.width() * scaleX) / scale,
          height_mm: (node.height() * scaleY) / scale,
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
      return;
    }
    const hits = marqueeHits(layers, rect, { insideGroupId });
    setSelectedIds((prev) => (band.additive ? new Set([...prev, ...hits]) : new Set(hits)));
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
      if (isBackground(e)) setSelectedIds(new Set());
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
      if (isInput) return;

      const modifier = e.ctrlKey || e.metaKey;

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

      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedIds.size > 0) {
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

  /** The bound thing, named the way a person recognises it. Never a UUID. */
  const selectedBindingLabel = !selectedData
    ? null
    : selectedData.kind === 'product'
      ? `${selectedData.product.code} - ${selectedData.product.name}`
      : selectedData.kind === 'set'
        ? `${selectedData.set.set_code} - ${selectedData.set.name}`
        : `${selectedData.line.code} - ${selectedData.line.name}`;

  const previewData = preview ? bindings.get(preview) : null;
  const previewLabel = !previewData
    ? preview
      ? 'loading'
      : null
    : previewData.kind === 'product'
      ? `${previewData.product.code} - ${previewData.product.name}`
      : previewData.kind === 'set'
        ? `${previewData.set.set_code} - ${previewData.set.name}`
        : `${previewData.line.code} - ${previewData.line.name}`;

  /** The bound product's photos, for the image picker's first tab. */
  const pickerProductImages = useMemo(() => {
    if (!imagePicker) return [];
    const layer = layers.find((l) => l.id === imagePicker.layerId);
    const data = layer ? dataOf(layer) : null;
    return data?.kind === 'product' ? data.product.images : [];
  }, [imagePicker, layers, dataOf]);

  // -- Render ----------------------------------------------------------------

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
        onAddPriceField={handleAddPriceField}
        onAddPriceBadge={handleAddPriceBadge}
        onAddBadge={handleAddBadge}
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
        previewLabel={previewLabel}
        onPreview={() => setPicker({ kind: 'preview' })}
        onClearPreview={() => setPreview(null)}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar: the host's rail, then the Layers panel */}
        <div className="hidden w-52 shrink-0 md:flex md:flex-col md:overflow-hidden">
          {leftRail}
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
        </div>

        {/* Centre: canvas workspace. The Stage fills it and the artboard sits at
            a pan offset inside (D33), so there is nothing to scroll. */}
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

                    {/* Layers */}
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
                      />
                    ))}

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

                    {/* ONE Transformer, after every layer, for the selection. */}
                    <Transformer
                      ref={transformerRef}
                      rotateEnabled
                      keepRatio={false}
                      listening={!handMode}
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
                <ContextMenuSeparator />
                <ContextMenuItem onSelect={() => setPicker({ kind: 'preview' })}>
                  <Eye />
                  Preview with a product
                </ContextMenuItem>
              </>
            )}
          </ContextMenuContent>
        </ContextMenu>

        {/* Right sidebar: Inspector panel */}
        <div className="hidden w-60 shrink-0 lg:block">
          <InspectorPanel
            layer={selectedLayer}
            onUpdate={updateLayer}
            onUpdateProps={updateLayerProps}
            resolvedText={selectedResolvedText}
            bindingLabel={selectedBindingLabel}
            fontOptions={library.fontOptions}
            onUploadFont={() => setFontUploadOpen(true)}
            onChooseImage={handleChooseImage}
            onChooseBadge={handleChooseBadge}
            onRebind={handleRebind}
            onRelinkGroup={handleRelinkGroup}
            onUseTemplate={onUseTemplate}
          />
        </div>
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
                ? previewMode
                : 'product'
        }
        multiple={picker.kind === 'alternatives' || picker.kind === 'accessories'}
        title={
          picker.kind === 'add-set'
            ? 'Add a product set'
            : picker.kind === 'rebind'
              ? 'Change what this block is about'
              : picker.kind === 'preview'
                ? 'Preview this template with'
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

'use client';

/**
 * Main tag template canvas editor shell.
 *
 * Left sidebar: layers panel. Center: Konva Stage with rulers. Right sidebar:
 * inspector panel. Top: toolbar with add/undo/redo/zoom/actions.
 *
 * All layer positions and sizes are in mm. The canvas converts to pixels using
 * a zoom-dependent scale factor. State is local (React state); saved on
 * explicit "Save" button click.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type Konva from 'konva';
import type {
  GroupBinding,
  ImageSource,
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
import { AssetPickerDialog } from './AssetPickerDialog';
import { FontUploadDialog } from './FontUploadDialog';
import { ProductPickDialog, type PickMode } from './ProductPickDialog';
import { useKitLibrary, useTagBindings } from './useTagBindings';
import { getProductTagData } from '../../services/tagDataService';
import { CanvasToolbar } from './CanvasToolbar';
import { CanvasRulers, RULER_THICKNESS } from './CanvasRulers';
import { LayersPanel } from './LayersPanel';
import { InspectorPanel } from './InspectorPanel';
import { useCanvasHistory } from './useCanvasHistory';
import { useSnapGuides } from './useSnapGuides';

// This component is loaded with ssr:false by the page, so direct imports are safe.
import { Stage, Layer as KonvaLayer, Rect, Line } from 'react-konva';
import { KonvaTagLayer } from './KonvaTagLayer';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let idCounter = 0;
function newLayerId(): string {
  idCounter += 1;
  return `layer-${Date.now()}-${idCounter}`;
}

const ZOOM_STEP = 0.1;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;
const DEFAULT_SCALE = 3; // 3 px per mm at 100% zoom

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
}

/** What the canvas is currently asking the user to pick. */
type PickerState =
  | { kind: 'none' }
  | { kind: 'add-product' }
  | { kind: 'add-set' }
  | { kind: 'rebind'; groupId: string; mode: PickMode }
  | { kind: 'alternatives' }
  | { kind: 'accessories' };

export function TagCanvasEditor({ doc, onChange, promotionId }: TagCanvasEditorProps) {
  const [layers, setLayers] = useState<TagLayer[]>(doc.layers);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [zoom, setZoom] = useState(1);
  const [clipboard, setClipboard] = useState<TagLayer[] | null>(null);
  const [picker, setPicker] = useState<PickerState>({ kind: 'none' });
  const [pickerBusy, setPickerBusy] = useState(false);
  const [imagePicker, setImagePicker] = useState<
    { layerId: string; badge: boolean } | null
  >(null);
  const [fontUploadOpen, setFontUploadOpen] = useState(false);

  const bindings = useTagBindings(promotionId);
  const library = useKitLibrary();

  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage | null>(null);

  const history = useCanvasHistory(doc.layers);
  const { computeSnap, guides, clearGuides } = useSnapGuides();

  const scale = DEFAULT_SCALE * zoom;
  const canvasWidthPx = doc.width_mm * scale;
  const canvasHeightPx = doc.height_mm * scale;

  // -- Layer mutations -------------------------------------------------------

  const updateLayer = useCallback(
    (id: string, changes: Partial<TagLayer>) => {
      setLayers((prev) => {
        const next = prev.map((l) => (l.id === id ? { ...l, ...changes } : l));
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

  const deleteSelectedLayers = useCallback(() => {
    if (selectedIds.size === 0) return;
    setLayers((prev) => {
      const next = prev.filter((l) => !selectedIds.has(l.id));
      history.pushState(next);
      return next;
    });
    setSelectedIds(new Set());
  }, [selectedIds, history]);

  const duplicateSelectedLayers = useCallback(() => {
    if (selectedIds.size === 0) return;
    setLayers((prev) => {
      const newLayers: TagLayer[] = [];
      const idMap = new Map<string, string>();

      for (const l of prev) {
        if (selectedIds.has(l.id)) {
          const newId = newLayerId();
          idMap.set(l.id, newId);
          newLayers.push({
            ...structuredClone(l),
            id: newId,
            x_mm: l.x_mm + 5,
            y_mm: l.y_mm + 5,
          });
        }
      }
      const next = [...prev, ...newLayers];
      history.pushState(next);
      setSelectedIds(new Set(newLayers.map((l) => l.id)));
      return next;
    });
  }, [selectedIds, history]);

  const groupSelectedLayers = useCallback(() => {
    if (selectedIds.size < 2) return;
    const ids = Array.from(selectedIds);
    const children = layers.filter((l) => ids.includes(l.id));
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
      props: { kind: 'group', children: ids },
    };

    setLayers((prev) => {
      const next = [...prev, groupLayer];
      history.pushState(next);
      return next;
    });
    setSelectedIds(new Set([groupId]));
  }, [selectedIds, layers, history]);

  const ungroupSelectedLayers = useCallback(() => {
    const groupLayers = layers.filter(
      (l) => selectedIds.has(l.id) && l.props.kind === 'group',
    );
    if (groupLayers.length === 0) return;

    const groupIds = new Set(groupLayers.map((l) => l.id));
    const childIds = new Set(
      groupLayers.flatMap((l) =>
        l.props.kind === 'group' ? l.props.children : [],
      ),
    );

    setLayers((prev) => {
      const next = prev.filter((l) => !groupIds.has(l.id));
      history.pushState(next);
      setSelectedIds(childIds);
      return next;
    });
  }, [selectedIds, layers, history]);

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
      if (layer.props.kind === 'group') return layer.props.binding;
      const group = groupOfChild.get(layer.id);
      return group && group.props.kind === 'group' ? group.props.binding : undefined;
    },
    [groupOfChild],
  );

  const dataOf = useCallback(
    (layer: TagLayer) => bindings.get(bindingOf(layer)),
    [bindings, bindingOf],
  );

  // Resolve whatever the document already carries, once, on open. A template
  // stores bindings and no values (ADR 0008), so without this every bound layer
  // would open showing the text it was created with.
  useEffect(() => {
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

  // -- Bound blocks (D27) ----------------------------------------------------

  const closePicker = useCallback(() => {
    setPicker({ kind: 'none' });
    setPickerBusy(false);
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
      setPicker({
        kind: 'rebind',
        groupId,
        mode: binding?.product_set_id ? 'set' : 'product',
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

  // -- Selection -------------------------------------------------------------

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

  const handleStageClick = useCallback((e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    // Deselect when clicking on the stage background.
    if (e.target === e.target.getStage()) {
      setSelectedIds(new Set());
    }
  }, []);

  // -- Drag and snap ---------------------------------------------------------

  const handleDragStart = useCallback(() => {
    // Nothing special, snap is computed on move.
  }, []);

  const handleDragMove = useCallback(
    (id: string, rawX: number, rawY: number) => {
      const layer = layers.find((l) => l.id === id);
      if (!layer) return;
      const result = computeSnap(
        id,
        rawX,
        rawY,
        layer.width_mm,
        layer.height_mm,
        layers,
        doc.width_mm,
        doc.height_mm,
      );
      // Update stage node position for the snap.
      const stageNode = stageRef.current;
      if (stageNode) {
        const konvaNode = stageNode.findOne(`#${id}`);
        if (konvaNode) {
          konvaNode.x(result.x_mm * scale);
          konvaNode.y(result.y_mm * scale);
        }
      }
    },
    [layers, computeSnap, doc.width_mm, doc.height_mm, scale],
  );

  const handleDragEnd = useCallback(
    (id: string) => {
      clearGuides();
      // Read final position from the Konva node.
      const stageNode = stageRef.current;
      if (stageNode) {
        const konvaNode = stageNode.findOne(`#${id}`);
        if (konvaNode) {
          updateLayer(id, {
            x_mm: konvaNode.x() / scale,
            y_mm: konvaNode.y() / scale,
          });
        }
      }
    },
    [clearGuides, scale, updateLayer],
  );

  const handleTransformEnd = useCallback(
    (
      id: string,
      attrs: {
        x_mm: number;
        y_mm: number;
        width_mm: number;
        height_mm: number;
        rotation_deg: number;
      },
    ) => {
      updateLayer(id, attrs);
    },
    [updateLayer],
  );

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

  // -- Zoom ------------------------------------------------------------------

  const handleZoomIn = useCallback(() => {
    setZoom((z) => Math.min(MAX_ZOOM, z + ZOOM_STEP));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoom((z) => Math.max(MIN_ZOOM, z - ZOOM_STEP));
  }, []);

  // -- Copy / Paste -----------------------------------------------------------

  const handleCopy = useCallback(() => {
    const sel = layers.filter((l) => selectedIds.has(l.id));
    if (sel.length > 0) setClipboard(structuredClone(sel));
  }, [layers, selectedIds]);

  const handlePaste = useCallback(() => {
    if (!clipboard || clipboard.length === 0) return;
    const newLayers = clipboard.map((l) => ({
      ...structuredClone(l),
      id: newLayerId(),
      x_mm: l.x_mm + 5,
      y_mm: l.y_mm + 5,
      z_index: maxZ,
    }));
    setLayers((prev) => {
      const next = [...prev, ...newLayers];
      history.pushState(next);
      return next;
    });
    setSelectedIds(new Set(newLayers.map((l) => l.id)));
  }, [clipboard, maxZ, history]);

  // -- Keyboard shortcuts ----------------------------------------------------

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isInput =
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement;
      if (isInput) return;

      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedIds.size > 0) {
        e.preventDefault();
        deleteSelectedLayers();
      }
      if (e.key === 'z' && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      }
      if (e.key === 'z' && (e.ctrlKey || e.metaKey) && e.shiftKey) {
        e.preventDefault();
        handleRedo();
      }
      if (e.key === 'y' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleRedo();
      }
      if (e.key === 'd' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        duplicateSelectedLayers();
      }
      if (e.key === 'g' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        groupSelectedLayers();
      }
      if (e.key === 'c' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleCopy();
      }
      if (e.key === 'v' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handlePaste();
      }
      // Nudge with arrow keys (1mm, or 0.1mm with shift).
      const nudge = e.shiftKey ? 0.1 : 1;
      if (e.key === 'ArrowLeft' && selectedIds.size > 0) {
        e.preventDefault();
        for (const id of selectedIds) {
          const layer = layers.find((l) => l.id === id);
          if (layer && !layer.locked) updateLayer(id, { x_mm: layer.x_mm - nudge });
        }
      }
      if (e.key === 'ArrowRight' && selectedIds.size > 0) {
        e.preventDefault();
        for (const id of selectedIds) {
          const layer = layers.find((l) => l.id === id);
          if (layer && !layer.locked) updateLayer(id, { x_mm: layer.x_mm + nudge });
        }
      }
      if (e.key === 'ArrowUp' && selectedIds.size > 0) {
        e.preventDefault();
        for (const id of selectedIds) {
          const layer = layers.find((l) => l.id === id);
          if (layer && !layer.locked) updateLayer(id, { y_mm: layer.y_mm - nudge });
        }
      }
      if (e.key === 'ArrowDown' && selectedIds.size > 0) {
        e.preventDefault();
        for (const id of selectedIds) {
          const layer = layers.find((l) => l.id === id);
          if (layer && !layer.locked) updateLayer(id, { y_mm: layer.y_mm + nudge });
        }
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [
    selectedIds,
    deleteSelectedLayers,
    duplicateSelectedLayers,
    groupSelectedLayers,
    handleUndo,
    handleRedo,
    handleCopy,
    handlePaste,
    layers,
    updateLayer,
  ]);

  // -- Expose current doc for save ------------------------------------------

  /** Call onChange with the current layers state. */
  const save = useCallback(() => {
    onChange({ ...doc, layers });
  }, [doc, layers, onChange]);

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

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <CanvasToolbar
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
        zoom={zoom}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onDeleteSelected={deleteSelectedLayers}
        onDuplicateSelected={duplicateSelectedLayers}
        onGroupSelected={groupSelectedLayers}
        onUngroupSelected={ungroupSelectedLayers}
        hasSelection={selectedIds.size > 0}
        hasMultiSelection={selectedIds.size >= 2}
        selectionIsGroup={selectionIsGroup}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar: Layers panel */}
        <div className="hidden w-52 shrink-0 md:block">
          <LayersPanel
            layers={layers}
            selectedIds={selectedIds}
            onSelect={handleSelect}
            onToggleVisibility={handleToggleVisibility}
            onToggleLock={handleToggleLock}
          />
        </div>

        {/* Center: Canvas workspace */}
        <div
          ref={containerRef}
          className="relative flex-1 overflow-auto bg-muted/50"
        >
          {/* Rulers */}
          <CanvasRulers
            widthMm={doc.width_mm}
            heightMm={doc.height_mm}
            scale={scale}
          />

          {/* Canvas container */}
          <div
            className="relative"
            style={{
              marginLeft: RULER_THICKNESS,
              marginTop: RULER_THICKNESS,
              width: canvasWidthPx,
              height: canvasHeightPx,
            }}
          >
            <Stage
              ref={stageRef as React.RefObject<Konva.Stage>}
              width={canvasWidthPx}
              height={canvasHeightPx}
              onClick={handleStageClick}
              onTap={handleStageClick}
            >
              <KonvaLayer>
                {/* White tag background */}
                <Rect
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
                    isSelected={selectedIds.has(layer.id)}
                    onSelect={handleSelect}
                    onDragStart={handleDragStart}
                    onDragMove={handleDragMove}
                    onDragEnd={handleDragEnd}
                    onTransformEnd={handleTransformEnd}
                  />
                ))}

                {/* Snap guides */}
                {guides.map((g, i) =>
                  g.orientation === 'vertical' ? (
                    <Line
                      key={`guide-v-${i}`}
                      points={[g.position_mm * scale, 0, g.position_mm * scale, canvasHeightPx]}
                      stroke="#f43f5e"
                      strokeWidth={0.5}
                      dash={[4, 4]}
                    />
                  ) : (
                    <Line
                      key={`guide-h-${i}`}
                      points={[0, g.position_mm * scale, canvasWidthPx, g.position_mm * scale]}
                      stroke="#f43f5e"
                      strokeWidth={0.5}
                      dash={[4, 4]}
                    />
                  ),
                )}
              </KonvaLayer>
            </Stage>
          </div>
        </div>

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
              : 'product'
        }
        multiple={picker.kind === 'alternatives' || picker.kind === 'accessories'}
        title={
          picker.kind === 'add-set'
            ? 'Add a product set'
            : picker.kind === 'rebind'
              ? 'Change what this block is about'
              : picker.kind === 'alternatives'
                ? 'Add an alternatives row'
                : picker.kind === 'accessories'
                  ? 'Add an accessories strip'
                  : 'Add a product'
        }
        confirmLabel={picker.kind === 'rebind' ? 'Rebind' : 'Add'}
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

      {/* Save bar (sticky bottom) */}
      <div className="flex h-10 shrink-0 items-center justify-end gap-2 border-t bg-background px-4">
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

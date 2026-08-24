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
import type { TagLayer, TagLayerProps, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import {
  defaultTextProps,
  defaultShapeProps,
  defaultImageProps,
  defaultProductSlotProps,
  defaultPriceFieldProps,
  defaultBadgeProps,
} from '@/lib/dealer-kit/tag-template-types';
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
}

export function TagCanvasEditor({ doc, onChange }: TagCanvasEditorProps) {
  const [layers, setLayers] = useState<TagLayer[]>(doc.layers);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [zoom, setZoom] = useState(1);
  const [clipboard, setClipboard] = useState<TagLayer[] | null>(null);

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

  const handleAddBadge = useCallback(() => {
    addLayer({ ...makeBaseLayer('badge', 15, 15), props: defaultBadgeProps() });
  }, [addLayer, makeBaseLayer]);

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

  const selectionIsGroup =
    selectedLayer?.props.kind === 'group';

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
        onAddBadge={handleAddBadge}
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
          />
        </div>
      </div>

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

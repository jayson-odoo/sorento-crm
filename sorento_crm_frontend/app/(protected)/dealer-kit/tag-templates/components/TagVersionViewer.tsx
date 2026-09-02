'use client';

/**
 * A past version's document, drawn read-only (D16, AC-S5-8).
 *
 * Deliberately NOT `TagCanvasEditor` in a locked mode: that component owns
 * selection, drag, the layers/inspector panels and a save bar, none of which a
 * history view needs, and disabling all of it in place would be a bigger and
 * riskier change than drawing the layers again. This mirrors the sheet's own
 * static tag render (`ArrangeSheetView`'s `PlacedTagNode`): a Stage with every
 * `KonvaTagLayer` `draggable={false}` / `listening={false}`, fit to the
 * container once. No bindings are resolved - a template document carries no
 * live product, so this draws exactly what the template editor's own canvas
 * shows for an unbound layer (dashed placeholders and all).
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { History, Undo2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { layerDisplay } from '@/lib/dealer-kit/product-block';
import {
  fitView,
  CANVAS_PX_PER_MM,
  type CanvasView,
} from '@/lib/dealer-kit/canvas-geometry';
import { useKitLibrary } from './useTagBindings';

// Loaded with ssr:false by the page, same as TagCanvasEditor.
import { Stage, Layer as KonvaLayer, Rect } from 'react-konva';
import { KonvaTagLayer } from './KonvaTagLayer';

function sortedByZ(layers: TagLayer[]): TagLayer[] {
  return [...layers].sort((a, b) => a.z_index - b.z_index);
}

export function TagVersionViewer({
  doc,
  versionNo,
  onBackToDraft,
  onRestore,
  restoring,
}: {
  doc: TagTemplateDoc;
  versionNo: number;
  onBackToDraft: () => void;
  onRestore: () => void;
  restoring?: boolean;
}) {
  const library = useKitLibrary();
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
  const [view, setView] = useState<CanvasView>({ zoom: 1, panX: 0, panY: 0 });

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

  useEffect(() => {
    if (containerSize.width <= 0 || containerSize.height <= 0) return;
    setView(
      fitView(containerSize, { width_mm: doc.width_mm, height_mm: doc.height_mm }),
    );
    // Re-fit whenever the version being viewed changes, not on every resize
    // tick - a viewer that keeps re-centring under the pointer would be worse
    // than one that only settles once per version.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerSize.width, containerSize.height, doc.width_mm, doc.height_mm]);

  const scale = CANVAS_PX_PER_MM * view.zoom;
  const layers = useMemo(() => sortedByZ(doc.layers), [doc.layers]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b bg-amber-50 px-4 py-2 dark:bg-amber-950/30">
        <div className="flex items-center gap-2 text-sm font-medium text-amber-800 dark:text-amber-300">
          <History className="size-4" />
          Viewing v{versionNo} - read-only
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onBackToDraft}>
            Back to draft
          </Button>
          <Button size="sm" onClick={onRestore} disabled={restoring}>
            <Undo2 className="size-3.5" />
            {restoring ? 'Restoring...' : 'Restore this version'}
          </Button>
        </div>
      </div>

      <div ref={containerRef} className="relative flex-1 overflow-hidden bg-muted/30">
        {containerSize.width > 0 && containerSize.height > 0 && (
          <Stage width={containerSize.width} height={containerSize.height} listening={false}>
            <KonvaLayer x={view.panX} y={view.panY}>
              <Rect
                x={0}
                y={0}
                width={doc.width_mm * scale}
                height={doc.height_mm * scale}
                fill="#ffffff"
                stroke="#d4d4d8"
                strokeWidth={1}
              />
              {layers
                .filter((l) => l.visible)
                .map((layer) => (
                  <KonvaTagLayer
                    key={layer.id}
                    layer={layer}
                    scale={scale}
                    display={layerDisplay(layer, null, library.assetUrls)}
                    draggable={false}
                    listening={false}
                  />
                ))}
            </KonvaLayer>
          </Stage>
        )}
      </div>
    </div>
  );
}

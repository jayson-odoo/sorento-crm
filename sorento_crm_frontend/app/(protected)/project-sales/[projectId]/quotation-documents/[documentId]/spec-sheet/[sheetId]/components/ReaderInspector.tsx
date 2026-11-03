'use client';

import * as React from 'react';

import { Button } from '@/components/ui/button';
import { InspectorPanel } from '@/app/(protected)/dealer-kit/tag-templates/components/InspectorPanel';
import { useKitLibrary } from '@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings';
import type { EmbeddedController } from '@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor';
import type {
  TagLayer,
  TagLayerProps,
} from '@/lib/dealer-kit/tag-template-types';

import type { ApplyAllChanges } from '../../../../../../_shared/services/specSheetService';
import { applicableChanges } from './selectionTools';

export type ApplyMode = 'page' | 'all';

/**
 * The designer's own Inspector for the selected layer of the page being edited, plus the one
 * choice the reader adds: apply a change to this page only (the default) or to every page of the
 * sheet. The change always lands on the page's canvas; "every page" also sends it to the server,
 * which moves or restyles that layer on every page that has it.
 */
export function ReaderInspector({
  pageKey,
  layer,
  layers,
  controller,
  mode,
  onModeChange,
  onApplyAll,
}: {
  pageKey: string | null;
  layer: TagLayer | null;
  layers: TagLayer[];
  controller: EmbeddedController | null;
  mode: ApplyMode;
  onModeChange: (mode: ApplyMode) => void;
  onApplyAll: (layerId: string, changes: ApplyAllChanges) => void;
}) {
  const library = useKitLibrary();

  const onUpdate = React.useCallback(
    (id: string, changes: Partial<TagLayer>) => {
      controller?.updateLayer(id, changes);
      if (mode === 'all') {
        const sent = applicableChanges(changes, null);
        if (sent) onApplyAll(id, sent);
      }
    },
    [controller, mode, onApplyAll],
  );
  const onUpdateProps = React.useCallback(
    (id: string, changes: Partial<TagLayerProps>) => {
      controller?.updateLayerProps(id, changes);
      if (mode === 'all') {
        const sent = applicableChanges(null, changes);
        if (sent) onApplyAll(id, sent);
      }
    },
    [controller, mode, onApplyAll],
  );

  return (
    <div
      className="flex min-h-0 flex-col gap-2"
      data-testid="reader-inspector"
      data-page-key={pageKey ?? ''}
    >
      {layer && (
        <div
          className="flex items-center gap-1 px-2 pt-2"
          role="group"
          aria-label="Apply to"
        >
          <span className="me-1 text-xs text-muted-foreground">Apply to</span>
          <Button
            type="button"
            size="sm"
            variant={mode === 'page' ? 'primary' : 'outline'}
            aria-pressed={mode === 'page'}
            onClick={() => onModeChange('page')}
          >
            This page
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === 'all' ? 'primary' : 'outline'}
            aria-pressed={mode === 'all'}
            onClick={() => onModeChange('all')}
          >
            Every page
          </Button>
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <InspectorPanel
          layer={layer}
          onUpdate={onUpdate}
          onUpdateProps={onUpdateProps}
          layers={layers}
          fontOptions={library.fontOptions}
          specSheet
          specKeys={library.specKeys}
        />
      </div>
    </div>
  );
}

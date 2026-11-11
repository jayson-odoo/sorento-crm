'use client';

import * as React from 'react';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import type { PoLinkKind } from '../../_shared/po-link/poLinkWording';

/** Right-click a worklist row for the PO link items on that one row. Rows carry
 *  `data-oi-row-id`; with `enabled` off the grid renders untouched. */
export function OiRowMenu({
  enabled,
  onRow,
  onPick,
  children,
}: {
  enabled: boolean;
  onRow: (rowId: string) => void;
  onPick: (kind: PoLinkKind) => void;
  children: React.ReactNode;
}) {
  if (!enabled) return <>{children}</>;
  return (
    <ContextMenu modal={false}>
      <ContextMenuTrigger asChild>
        <div
          // Capture phase: a right-click outside a row stops here, so the browser's own menu
          // shows instead of an empty one.
          onContextMenuCapture={(event) => {
            const rowEl = (event.target as Element).closest('[data-oi-row-id]');
            const id = rowEl?.getAttribute('data-oi-row-id');
            if (!id) {
              event.stopPropagation();
              return;
            }
            onRow(id);
          }}
        >
          {children}
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent className="w-56">
        <ContextMenuItem onSelect={() => onPick('link')}>Link to PO...</ContextMenuItem>
        <ContextMenuItem onSelect={() => onPick('change')}>Change PO...</ContextMenuItem>
        <ContextMenuItem onSelect={() => onPick('unlink')}>Unlink from PO...</ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}

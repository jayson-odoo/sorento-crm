'use client';

import { Fragment } from 'react';
import { useDroppable } from '@dnd-kit/core';
import { ChevronRight, Home } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { BreadcrumbCrumb } from './drivePath';

// Distinct from the tree's `folder-` (a path ancestor appears in both the
// breadcrumb and the expanded tree - same id would collide in dnd-kit). Must
// match DND_ID_CRUMB_FOLDER_PREFIX in AttachmentDirectoriesView.
const FOLDER_DROP_PREFIX = 'crumbfolder-';
const FOLDER_ALL_ID = 'crumbfolder-all';

function CrumbButton({
  crumb,
  isCurrent,
  droppable,
  onNavigate,
}: {
  crumb: BreadcrumbCrumb;
  isCurrent: boolean;
  droppable: boolean;
  onNavigate: (id: string | null) => void;
}) {
  const dropId = crumb.id == null ? FOLDER_ALL_ID : `${FOLDER_DROP_PREFIX}${crumb.id}`;
  const { setNodeRef, isOver } = useDroppable({
    id: dropId,
    data: { type: 'folder', directoryId: crumb.id },
    disabled: !droppable,
  });

  return (
    <button
      ref={droppable ? setNodeRef : undefined}
      type="button"
      onClick={() => onNavigate(crumb.id)}
      title={crumb.name}
      className={cn(
        'flex items-center gap-1 rounded px-1.5 py-0.5 max-w-[160px] truncate',
        isCurrent
          ? 'font-medium text-foreground'
          : 'text-muted-foreground hover:text-foreground hover:bg-muted',
        isOver && 'ring-2 ring-primary ring-inset bg-primary/10'
      )}
    >
      {crumb.id == null && <Home className="size-3.5 shrink-0" />}
      <span className="truncate">{crumb.name}</span>
    </button>
  );
}

/**
 * Drive breadcrumb (UAC A2). Each crumb navigates; each is also a drop target so
 * a dragged file/folder can be moved into that ancestor (UAC E2). Drop targets
 * are disabled on touch (`droppable=false`) so mobile relies on the Move dialog.
 */
export default function DriveBreadcrumb({
  crumbs,
  onNavigate,
  droppable = true,
}: {
  crumbs: BreadcrumbCrumb[];
  onNavigate: (id: string | null) => void;
  droppable?: boolean;
}) {
  return (
    <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-0.5 text-sm">
      {crumbs.map((crumb, idx) => {
        const isCurrent = idx === crumbs.length - 1;
        return (
          <Fragment key={crumb.id ?? '__root__'}>
            {idx > 0 && <ChevronRight className="size-3.5 text-muted-foreground shrink-0" />}
            <CrumbButton
              crumb={crumb}
              isCurrent={isCurrent}
              droppable={droppable}
              onNavigate={onNavigate}
            />
          </Fragment>
        );
      })}
    </nav>
  );
}

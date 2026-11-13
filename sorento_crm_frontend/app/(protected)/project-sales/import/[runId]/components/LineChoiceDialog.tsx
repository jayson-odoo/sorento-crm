'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useLineTargetOptions } from '../../../_shared/hooks/useProjectImport';
import type {
  ProjectImportAction,
  ProjectImportKind,
} from '../../../_shared/types/projectImport.types';

export type LineChoice = { action: ProjectImportAction; target_id: string | null; new_title: string | null };

/** AC-PI-16: what a line of each kind may be set to. */
export const ACTIONS_BY_KIND: Record<ProjectImportKind, ProjectImportAction[]> = {
  customer: ['link', 'skip'],
  project: ['link', 'create', 'skip'],
  developer: ['link', 'create', 'none'],
  person: ['link', 'none'],
};

export const ACTION_LABELS: Record<ProjectImportAction, string> = {
  link: 'Link to…',
  create: 'Create new',
  skip: 'Skip',
  none: 'None',
};

const PICK_LABEL: Record<ProjectImportKind, string> = {
  customer: 'Customer',
  project: 'Project',
  developer: 'Developer',
  person: 'User',
};

/**
 * One choice for one line, or for every ticked line (the bulk "Set to"). The picker is the
 * kind's own: customers, projects, developer parties or users.
 */
export function LineChoiceDialog({
  open,
  kind,
  action,
  title,
  initialTitle,
  busy,
  onCancel,
  onSave,
}: {
  open: boolean;
  kind: ProjectImportKind;
  action: 'link' | 'create';
  title: string;
  initialTitle?: string | null;
  busy?: boolean;
  onCancel: () => void;
  onSave: (choice: LineChoice) => void;
}) {
  const fetchOptions = useLineTargetOptions(kind);
  const [target, setTarget] = React.useState('');
  const [newTitle, setNewTitle] = React.useState(initialTitle ?? '');

  React.useEffect(() => {
    if (open) {
      setTarget('');
      setNewTitle(initialTitle ?? '');
    }
  }, [open, initialTitle]);

  const ready = action === 'link' ? Boolean(target) : Boolean(newTitle.trim());

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="w-full max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-3">
          {action === 'link' ? (
            <div className="space-y-1.5">
              <Label htmlFor="line-target">{PICK_LABEL[kind]}</Label>
              <SearchableSelect
                id="line-target"
                value={target}
                onChange={setTarget}
                fetchOptions={(query) => fetchOptions(query)}
                clearable
                placeholder={`Pick a ${PICK_LABEL[kind].toLowerCase()}`}
                aria-label={PICK_LABEL[kind]}
              />
            </div>
          ) : kind === 'project' ? (
            <div className="space-y-1.5">
              <Label htmlFor="line-title">Project title</Label>
              <Input
                id="line-title"
                value={newTitle}
                onChange={(event) => setNewTitle(event.target.value)}
              />
            </div>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            disabled={!ready || busy}
            onClick={() =>
              onSave({
                action,
                target_id: action === 'link' ? target : null,
                new_title: action === 'create' && kind === 'project' ? newTitle.trim() : null,
              })
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

'use client';

import * as React from 'react';
import Link from 'next/link';
import { Pencil, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  RegisteredProjectSelect,
  registeredProjectOption,
} from '@/components/common/RegisteredProjectSelect';
import { useSetRecordProject } from '@/hooks/useSetRecordProject';
import type { RecordProjectKind } from '@/services/recordProjectService';

/**
 * A record's "Registered project" on its own page (PROJECT-RELATED-RECORDS AC-C6, AC-C7, D2):
 * the linked project's code and title, opening the project. Someone who may edit the record
 * changes it in place, at any status and without Revise; the change lands in History.
 */
export function RecordProjectField({
  kind,
  recordId,
  projectId,
  projectCode,
  projectTitle,
  canEdit,
  onSaved,
}: {
  kind: RecordProjectKind;
  recordId: string;
  projectId: string | null | undefined;
  projectCode: string | null | undefined;
  projectTitle: string | null | undefined;
  canEdit: boolean;
  /** Refresh the record, so the page shows the new link. */
  onSaved?: () => void;
}) {
  const [editing, setEditing] = React.useState(false);
  const save = useSetRecordProject(kind, recordId);
  const label = [projectCode, projectTitle].filter(Boolean).join(' - ');

  if (editing) {
    return (
      <div className="flex min-w-0 items-center gap-2">
        <div className="min-w-0 flex-1">
          <RegisteredProjectSelect
            value={projectId}
            aria-label="Registered project"
            disabled={save.isPending}
            selectedOption={registeredProjectOption(projectId, projectCode, projectTitle)}
            onChange={(next) => {
              if ((next ?? null) === (projectId ?? null)) return;
              save.mutate(next, {
                onSuccess: () => {
                  setEditing(false);
                  onSaved?.();
                },
              });
            }}
          />
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          mode="icon"
          aria-label="Stop changing the project"
          onClick={() => setEditing(false)}
        >
          <X className="size-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className="flex min-w-0 items-center gap-2">
      {projectId && label ? (
        <Link
          href={`/project-sales/${projectId}`}
          className="min-w-0 truncate text-sm font-medium text-primary hover:underline"
          title={label}
        >
          {label}
        </Link>
      ) : (
        <span className="text-sm text-muted-foreground">-</span>
      )}
      {canEdit && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          mode="icon"
          aria-label="Change the project"
          onClick={() => setEditing(true)}
        >
          <Pencil className="size-4" />
        </Button>
      )}
    </div>
  );
}

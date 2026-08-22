'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useProjectTypeMutations } from '../../_shared/hooks/useProjects';
import type { ProjectType } from '../../_shared/types/project.types';

/**
 * The code is immutable in practice: reporting groups by it and the seeder recognises
 * its own rows by it. Editable on create, locked afterwards, so a rename of the display
 * name never silently re-partitions a report.
 */
export function ProjectTypeDialog({
  type,
  onDone,
}: {
  type: ProjectType | null;
  onDone: () => void;
}) {
  const { create, update } = useProjectTypeMutations();
  const [name, setName] = React.useState(type?.name ?? '');
  const [code, setCode] = React.useState(type?.code ?? '');
  const [description, setDescription] = React.useState(type?.description ?? '');
  const [derives, setDerives] = React.useState(type?.derives_delivery_from_launch ?? false);
  const [isActive, setIsActive] = React.useState(type?.is_active ?? true);

  const isEdit = Boolean(type);
  const pending = create.isPending || update.isPending;

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit ${type?.name}` : 'Add a project type'}</DialogTitle>
          <DialogDescription>
            The kind of job. It decides which templates a project can use, and whether
            the delivery window is inferred from the launch date.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const body = {
              name: name.trim(),
              code: code.trim(),
              description: description.trim() || null,
              derives_delivery_from_launch: derives,
              is_active: isActive,
            };
            if (type) {
              // The code is fixed after creation, so it is never sent on an update.
              const editable = {
                name: body.name,
                description: body.description,
                derives_delivery_from_launch: body.derives_delivery_from_launch,
                is_active: body.is_active,
              };
              await update.mutateAsync({ id: type.id, body: editable });
            } else {
              await create.mutateAsync(body);
            }
            onDone();
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="type-name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="type-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Hotel"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="type-code">
                Code <span className="text-destructive">*</span>
              </Label>
              <Input
                id="type-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                placeholder="hotel"
                disabled={isEdit}
                required
              />
              <p className="text-xs text-muted-foreground">
                {isEdit
                  ? 'The code is fixed after creation. Reports group by it.'
                  : 'Lower case, no spaces. Reports group by it, so it does not change later.'}
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="type-description">Description</Label>
              <Textarea
                id="type-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={2}
              />
            </div>

            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={derives}
                onChange={(event) => setDerives(event.target.checked)}
                className="mt-0.5 size-4 rounded border-border"
              />
              <span>
                Infer the delivery window from the launch date
                <span className="block text-xs text-muted-foreground">
                  Property developments hand over a known lag after launch. Every other
                  type has to state the window, so registration asks for it explicitly.
                </span>
              </span>
            </label>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(event) => setIsActive(event.target.checked)}
                className="size-4 rounded border-border"
              />
              Active. Inactive types stay on their projects but stop appearing in pickers
            </label>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || !code.trim() || pending}>
              {isEdit ? 'Save changes' : 'Add type'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

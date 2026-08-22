'use client';

import * as React from 'react';
import { Plus, X } from 'lucide-react';
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
import { useProjectTemplateMutations } from '../../_shared/hooks/useProjects';
import type { ProjectTemplate } from '../../_shared/types/project.types';

const DEFAULT_ROLES = ['Decision Maker', 'Influencer', 'Info Provider', 'Architect'];

/**
 * Template plus the stakeholder roles it offers, edited together.
 *
 * The role list is sent WHOLE, not as a delta. The server reconciles by name and
 * deactivates rather than deletes a role that stakeholders still reference, so removing
 * one here never orphans a recorded stakeholder.
 */
export function ProjectTemplateDialog({
  typeId,
  template,
  onDone,
}: {
  typeId: string;
  template: ProjectTemplate | null;
  onDone: () => void;
}) {
  const { create, update } = useProjectTemplateMutations();
  const [name, setName] = React.useState(template?.name ?? '');
  const [description, setDescription] = React.useState(template?.description ?? '');
  const [isActive, setIsActive] = React.useState(template?.is_active ?? true);
  const [roles, setRoles] = React.useState<string[]>(() =>
    template
      ? template.roles.filter((role) => role.is_active).map((role) => role.name)
      : [...DEFAULT_ROLES],
  );
  const [roleDraft, setRoleDraft] = React.useState('');

  const isEdit = Boolean(template);
  const pending = create.isPending || update.isPending;

  function addRole() {
    const value = roleDraft.trim();
    if (!value || roles.some((role) => role.toLowerCase() === value.toLowerCase())) {
      setRoleDraft('');
      return;
    }
    setRoles((previous) => [...previous, value]);
    setRoleDraft('');
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? `Edit ${template?.name}` : 'Add a template'}
          </DialogTitle>
          <DialogDescription>
            Templates are the variants within a type: New Build and Refurbishment work
            differently even though both are hotels.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const body = {
              type_id: typeId,
              name: name.trim(),
              description: description.trim() || null,
              is_active: isActive,
              role_names: roles,
            };
            if (template) {
              await update.mutateAsync({ id: template.id, body });
            } else {
              await create.mutateAsync(body);
            }
            onDone();
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="template-name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="template-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Refurbishment"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="template-description">Description</Label>
              <Textarea
                id="template-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={2}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="template-role">Stakeholder roles</Label>
              <div className="flex gap-2">
                <Input
                  id="template-role"
                  value={roleDraft}
                  onChange={(event) => setRoleDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      addRole();
                    }
                  }}
                  placeholder="Quantity Surveyor"
                />
                <Button type="button" variant="outline" onClick={addRole}>
                  <Plus className="size-4" aria-hidden />
                  Add
                </Button>
              </div>
              {roles.length === 0 ? (
                <p className="rounded-md border border-dashed border-border px-2.5 py-2 text-xs text-muted-foreground">
                  With no roles, a stakeholder on this template records with no role at
                  all. Add at least the decision maker.
                </p>
              ) : (
                <ul className="flex flex-wrap gap-1.5 pt-1">
                  {roles.map((role) => (
                    <li key={role}>
                      <span className="flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs">
                        {role}
                        <button
                          type="button"
                          onClick={() =>
                            setRoles((previous) => previous.filter((item) => item !== role))
                          }
                          aria-label={`Remove ${role}`}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <X className="size-3" />
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-muted-foreground">
                Removing a role that stakeholders already use deactivates it rather than
                deleting it, so those records keep their role.
              </p>
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(event) => setIsActive(event.target.checked)}
                className="size-4 rounded border-border"
              />
              Active. Inactive templates stay on their projects but stop appearing in
              pickers
            </label>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || pending}>
              {isEdit ? 'Save changes' : 'Add template'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

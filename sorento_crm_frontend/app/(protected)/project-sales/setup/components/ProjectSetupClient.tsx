'use client';

import * as React from 'react';
import { CalendarClock, Layers, Pencil, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  useProjectTemplateMutations,
  useProjectTemplates,
  useProjectTypeMutations,
  useProjectTypes,
} from '../../_shared/hooks/useProjects';
import type { ProjectTemplate, ProjectType } from '../../_shared/types/project.types';
import { ProjectTypeDialog } from './ProjectTypeDialog';
import { ProjectTemplateDialog } from './ProjectTemplateDialog';
import { TemplateChecklistPanel } from './TemplateChecklistPanel';

/**
 * Three levels of configuration on one screen, because they are only understandable
 * together: a TYPE (Hotel) holds TEMPLATES (New Build, Refurbishment), and a template
 * carries both the stakeholder ROLES it offers and the CHECKLIST a new project copies.
 *
 * Splitting these across three admin pages was the alternative. It hides the thing the
 * admin needs to see: which template a project gets, and therefore which checklist.
 */
export function ProjectSetupClient() {
  const types = useProjectTypes();
  const [selectedTypeId, setSelectedTypeId] = React.useState<string | null>(null);
  const templates = useProjectTemplates(selectedTypeId ?? undefined);
  const [selectedTemplateId, setSelectedTemplateId] = React.useState<string | null>(null);

  const typeMutations = useProjectTypeMutations();
  const templateMutations = useProjectTemplateMutations();

  const [typeDialog, setTypeDialog] = React.useState<{ type: ProjectType | null } | null>(null);
  const [templateDialog, setTemplateDialog] = React.useState<{
    template: ProjectTemplate | null;
  } | null>(null);
  const [deletingType, setDeletingType] = React.useState<ProjectType | null>(null);
  const [deletingTemplate, setDeletingTemplate] = React.useState<ProjectTemplate | null>(null);

  const typeRows = React.useMemo(() => types.data ?? [], [types.data]);
  const templateRows = React.useMemo(() => templates.data ?? [], [templates.data]);

  // Land on the first type so the screen is never three empty panes waiting on a click.
  React.useEffect(() => {
    if (!selectedTypeId && typeRows.length > 0) setSelectedTypeId(typeRows[0].id);
  }, [selectedTypeId, typeRows]);

  React.useEffect(() => {
    if (selectedTemplateId && !templateRows.some((row) => row.id === selectedTemplateId)) {
      setSelectedTemplateId(null);
    }
  }, [selectedTemplateId, templateRows]);

  const selectedTemplate = templateRows.find((row) => row.id === selectedTemplateId) ?? null;

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">Project setup</h1>
          <p className="text-sm text-muted-foreground">
            What kinds of project we pursue, and what a new one starts with.
          </p>
        </div>
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-sm">Project types</CardTitle>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setTypeDialog({ type: null })}
            >
              <Plus className="size-4" aria-hidden />
              Add
            </Button>
          </CardHeader>
          <CardContent>
            {types.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : typeRows.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center">
                <h3 className="text-sm font-semibold">No project types yet</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  A type is the kind of job: property development, hotel, fitout.
                </p>
                <Button
                  type="button"
                  className="mt-3"
                  onClick={() => setTypeDialog({ type: null })}
                >
                  <Plus className="size-4" aria-hidden />
                  Add the first type
                </Button>
              </div>
            ) : (
              <ul className="space-y-1.5">
                {typeRows.map((type) => (
                  <li key={type.id}>
                    <div
                      className={
                        selectedTypeId === type.id
                          ? 'flex items-center gap-2 rounded-lg border border-primary bg-primary/5 px-3 py-2'
                          : 'flex items-center gap-2 rounded-lg border border-border px-3 py-2'
                      }
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedTypeId(type.id)}
                        className="min-w-0 flex-1 text-left"
                        aria-current={selectedTypeId === type.id ? 'true' : undefined}
                      >
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span className="truncate text-sm font-medium" title={type.name}>
                            {type.name}
                          </span>
                          {!type.is_active && (
                            <Badge variant="outline" className="text-[11px]">
                              Inactive
                            </Badge>
                          )}
                          {type.derives_delivery_from_launch && (
                            <Badge variant="secondary" className="gap-1 text-[11px]">
                              <CalendarClock className="size-3" aria-hidden />
                              Delivery from launch
                            </Badge>
                          )}
                        </span>
                        <span className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                          <Layers className="size-3" aria-hidden />
                          {type.template_count ?? 0} template
                          {(type.template_count ?? 0) === 1 ? '' : 's'}
                        </span>
                      </button>
                      <div className="flex shrink-0 gap-1">
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setTypeDialog({ type })}
                          aria-label={`Edit ${type.name}`}
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeletingType(type)}
                          aria-label={`Delete ${type.name}`}
                        >
                          <Trash2 className="size-3.5 text-destructive" />
                        </Button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <CardTitle className="text-sm">Templates</CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">
                A template decides the stakeholder roles offered and the checklist a new
                project copies in.
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!selectedTypeId}
              onClick={() => setTemplateDialog({ template: null })}
            >
              <Plus className="size-4" aria-hidden />
              Add template
            </Button>
          </CardHeader>
          <CardContent>
            {!selectedTypeId ? (
              <p className="text-sm text-muted-foreground">
                Select a project type to see its templates.
              </p>
            ) : templates.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : templateRows.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center">
                <h3 className="text-sm font-semibold">This type has no templates</h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  Without one, a project of this type has no roles to pick from and no
                  checklist to start with.
                </p>
                <Button
                  type="button"
                  className="mt-3"
                  onClick={() => setTemplateDialog({ template: null })}
                >
                  <Plus className="size-4" aria-hidden />
                  Add the first template
                </Button>
              </div>
            ) : (
              <ul className="space-y-1.5">
                {templateRows.map((template) => (
                  <li key={template.id}>
                    <div
                      className={
                        selectedTemplateId === template.id
                          ? 'flex items-center gap-2 rounded-lg border border-primary bg-primary/5 px-3 py-2'
                          : 'flex items-center gap-2 rounded-lg border border-border px-3 py-2'
                      }
                    >
                      <button
                        type="button"
                        onClick={() =>
                          setSelectedTemplateId((previous) =>
                            previous === template.id ? null : template.id,
                          )
                        }
                        className="min-w-0 flex-1 text-left"
                      >
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span className="truncate text-sm font-medium" title={template.name}>
                            {template.name}
                          </span>
                          {!template.is_active && (
                            <Badge variant="outline" className="text-[11px]">
                              Inactive
                            </Badge>
                          )}
                          {template.has_forked_status_graph && (
                            <Badge variant="secondary" className="text-[11px]">
                              Own stage graph
                            </Badge>
                          )}
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                          {template.roles.filter((role) => role.is_active).length} roles:{' '}
                          {template.roles
                            .filter((role) => role.is_active)
                            .map((role) => role.name)
                            .join(', ') || 'none'}
                        </span>
                      </button>
                      <div className="flex shrink-0 gap-1">
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setTemplateDialog({ template })}
                          aria-label={`Edit ${template.name}`}
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeletingTemplate(template)}
                          aria-label={`Delete ${template.name}`}
                        >
                          <Trash2 className="size-3.5 text-destructive" />
                        </Button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {selectedTemplate ? (
        <TemplateChecklistPanel template={selectedTemplate} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Starting checklist</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Select a template above to edit the checklist every new project of that
              template copies in.
            </p>
          </CardContent>
        </Card>
      )}

      {typeDialog && (
        <ProjectTypeDialog type={typeDialog.type} onDone={() => setTypeDialog(null)} />
      )}

      {templateDialog && selectedTypeId && (
        <ProjectTemplateDialog
          typeId={selectedTypeId}
          template={templateDialog.template}
          onDone={() => setTemplateDialog(null)}
        />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deletingType)}
        onOpenChange={(next) => !next && setDeletingType(null)}
        title="Confirm delete"
        description={
          deletingType
            ? `Delete the project type "${deletingType.name}"? This action cannot be undone. A type still used by a template or a project cannot be deleted, so deactivate it instead.`
            : ''
        }
        onDelete={async () => {
          if (!deletingType) return;
          await typeMutations.remove.mutateAsync(deletingType.id);
        }}
        onSuccess={() => {
          if (deletingType?.id === selectedTypeId) setSelectedTypeId(null);
          setDeletingType(null);
        }}
        successMessage="Project type deleted"
      />

      <ConfirmDeleteDialog
        open={Boolean(deletingTemplate)}
        onOpenChange={(next) => !next && setDeletingTemplate(null)}
        title="Confirm delete"
        description={
          deletingTemplate
            ? `Delete the template "${deletingTemplate.name}"? This action cannot be undone, and its checklist goes with it. A template already used by a project cannot be deleted, so deactivate it instead.`
            : ''
        }
        onDelete={async () => {
          if (!deletingTemplate) return;
          await templateMutations.remove.mutateAsync(deletingTemplate.id);
        }}
        onSuccess={() => setDeletingTemplate(null)}
        successMessage="Template deleted"
      />
    </div>
  );
}

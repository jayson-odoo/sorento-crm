'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  listApprovedTemplates,
  PARAM_VARIABLES,
  setTemplateDefault,
  USE_CASES,
  type ParamVariable,
  type TemplateDefault,
  type UseCase,
} from '@/services/whatsappTemplateService';

interface SetDefaultTemplateDialogProps {
  useCase: UseCase;
  current: TemplateDefault | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function SetDefaultTemplateDialog({
  useCase,
  current,
  open,
  onOpenChange,
}: SetDefaultTemplateDialogProps) {
  const queryClient = useQueryClient();
  const [templateId, setTemplateId] = useState<string>(current?.template_id ?? '');
  const [mapping, setMapping] = useState<Record<string, ParamVariable | ''>>({});
  const [isSaving, setIsSaving] = useState(false);

  const { data: templates, isLoading } = useQuery({
    queryKey: ['whatsapp-templates', 'approved'],
    queryFn: listApprovedTemplates,
  });

  const selected = useMemo(
    () => (templates ?? []).find((t) => t.id === templateId) ?? null,
    [templates, templateId],
  );

  const paramKeys = useMemo(
    () =>
      selected
        ? Array.from({ length: selected.param_count }, (_, i) => String(i + 1))
        : [],
    [selected],
  );

  // Seed mapping when the template changes: keep current mapping when editing
  // the same template, start blank otherwise.
  useEffect(() => {
    if (!selected) {
      setMapping({});
      return;
    }
    const seed: Record<string, ParamVariable | ''> = {};
    for (const key of Array.from({ length: selected.param_count }, (_, i) => String(i + 1))) {
      seed[key] =
        current?.template_id === selected.id ? (current.param_mapping[key] ?? '') : '';
    }
    setMapping(seed);
  }, [selected, current]);

  const allMapped = paramKeys.length > 0 ? paramKeys.every((k) => mapping[k]) : true;
  const canSave = Boolean(templateId) && allMapped && !isSaving;

  const useCaseLabel = USE_CASES.find((u) => u.key === useCase)?.label ?? useCase;

  const handleSave = async () => {
    if (!templateId) return;
    setIsSaving(true);
    try {
      const cleanMapping: Record<string, ParamVariable> = {};
      for (const [k, v] of Object.entries(mapping)) {
        if (v) cleanMapping[k] = v;
      }
      await setTemplateDefault(useCase, {
        template_id: templateId,
        param_mapping: cleanMapping,
      });
      toast.success(`Default template for ${useCaseLabel} saved`);
      await queryClient.invalidateQueries({ queryKey: ['whatsapp-template-defaults'] });
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save default');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Default template — {useCaseLabel}</DialogTitle>
          <DialogDescription>
            Pick an approved template and map each placeholder to a CRM variable.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Template</Label>
            <Select value={templateId} onValueChange={setTemplateId} disabled={isLoading}>
              <SelectTrigger>
                <SelectValue placeholder={isLoading ? 'Loading…' : 'Select an approved template'} />
              </SelectTrigger>
              <SelectContent>
                {(templates ?? []).map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name} ({t.language})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selected && (
            <div className="rounded-md border bg-muted/40 p-3 text-sm whitespace-pre-wrap">
              {selected.body_text}
            </div>
          )}

          {paramKeys.length > 0 && (
            <div className="space-y-2">
              <Label>Parameter mapping</Label>
              <div className="space-y-2">
                {paramKeys.map((key) => (
                  <div key={key} className="flex items-center gap-3">
                    <span className="font-mono text-sm w-12 shrink-0">{`{{${key}}}`}</span>
                    <Select
                      value={mapping[key] ?? ''}
                      onValueChange={(v) =>
                        setMapping((prev) => ({ ...prev, [key]: v as ParamVariable }))
                      }
                    >
                      <SelectTrigger className="flex-1">
                        <SelectValue placeholder="Select variable" />
                      </SelectTrigger>
                      <SelectContent>
                        {PARAM_VARIABLES.map((v) => (
                          <SelectItem key={v.key} value={v.key} title={v.description}>
                            {v.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
              {!allMapped && (
                <p className="text-xs text-muted-foreground">
                  Map every placeholder before saving.
                </p>
              )}
            </div>
          )}

          {selected && paramKeys.length === 0 && (
            <p className="text-xs text-muted-foreground">
              This template has no parameters — nothing to map.
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!canSave}>
            {isSaving ? 'Saving…' : 'Save default'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  BUTTON_LINK_VARIABLES,
  BUTTON_URL_KEY,
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
    const sameTemplate = current?.template_id === selected.id;
    for (const key of Array.from({ length: selected.param_count }, (_, i) => String(i + 1))) {
      seed[key] = sameTemplate ? (current.param_mapping[key] ?? '') : '';
    }
    // COPY_CODE auth buttons carry no link variable - the OTP code auto-fills.
    if (selected.has_url_button && !selected.button_is_copy_code) {
      // Default the button link to portal_url for a fresh mapping.
      seed[BUTTON_URL_KEY] = sameTemplate
        ? (current.param_mapping[BUTTON_URL_KEY] ?? current.button_url_var ?? 'portal_url')
        : 'portal_url';
    }
    setMapping(seed);
  }, [selected, current]);

  const allMapped = paramKeys.length > 0 ? paramKeys.every((k) => mapping[k]) : true;
  const buttonMapped =
    !selected?.has_url_button ||
    selected.button_is_copy_code ||
    Boolean(mapping[BUTTON_URL_KEY]);
  // Chat reply templates MUST carry the typed message somewhere (variable: message).
  const isChat = useCase.endsWith('_chat');
  const messageMapped = paramKeys.some((k) => mapping[k] === 'message');
  const senderMapped = paramKeys.some((k) => mapping[k] === 'sender_name');
  const chatOk = !isChat || (Boolean(selected) && messageMapped);
  const canSave = Boolean(templateId) && allMapped && buttonMapped && chatOk && !isSaving;

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
          <DialogTitle>Default template - {useCaseLabel}</DialogTitle>
          <DialogDescription>
            Pick an approved template and map each placeholder to a CRM variable.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Template</Label>
            <SearchableSelect
              value={templateId}
              onChange={setTemplateId}
              disabled={isLoading}
              options={(templates ?? []).map((t) => ({
                value: t.id,
                label: `${t.name} (${t.language})`,
              }))}
              placeholder={isLoading ? 'Loading…' : 'Select an approved template'}
            />
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
                    <SearchableSelect
                      value={mapping[key] ?? ''}
                      onChange={(v) =>
                        setMapping((prev) => ({ ...prev, [key]: v as ParamVariable }))
                      }
                      options={PARAM_VARIABLES.map((v) => ({ value: v.key, label: v.label }))}
                      placeholder="Select variable"
                      triggerClassName="flex-1"
                    />
                  </div>
                ))}
              </div>
              {!allMapped && (
                <p className="text-xs text-muted-foreground">
                  Map every placeholder before saving.
                </p>
              )}
              {isChat && allMapped && !messageMapped && (
                <p className="text-xs text-destructive" data-testid="chat-message-required">
                  A chat reply template must map one placeholder to{' '}
                  <span className="font-medium">Full update message</span> (the typed text).
                </p>
              )}
              {isChat && messageMapped && !senderMapped && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  Tip: map a placeholder to <span className="font-medium">Sender name</span> so the
                  contact knows who replied.
                </p>
              )}
            </div>
          )}

          {selected?.has_url_button && selected.button_is_copy_code && (
            <div className="space-y-2">
              <Label>Button link</Label>
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs text-muted-foreground w-20 shrink-0 truncate" title={selected.button_text ?? 'Copy code'}>
                  {selected.button_text ?? 'Copy code'} →
                </span>
                <span className="text-sm text-muted-foreground">Copies the OTP code</span>
              </div>
              <p className="text-xs text-muted-foreground">
                This is a WhatsApp Authentication copy-code button - it copies the verification
                code automatically. No variable to map.
              </p>
            </div>
          )}

          {selected?.has_url_button && !selected.button_is_copy_code && (
            <div className="space-y-2">
              <Label>Button link</Label>
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs text-muted-foreground w-20 shrink-0 truncate" title={selected.button_text ?? 'URL button'}>
                  {selected.button_text ?? 'URL'} →
                </span>
                <SearchableSelect
                  value={mapping[BUTTON_URL_KEY] ?? ''}
                  onChange={(v) =>
                    setMapping((prev) => ({ ...prev, [BUTTON_URL_KEY]: v as ParamVariable }))
                  }
                  options={PARAM_VARIABLES.filter((v) => BUTTON_LINK_VARIABLES.includes(v.key)).map(
                    (v) => ({ value: v.key, label: v.label }),
                  )}
                  placeholder="Select link variable"
                  triggerClassName="flex-1"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                The button opens{' '}
                <span className="font-mono">{selected.button_url_base ?? ''}</span>
                <span className="font-mono">{'{link}'}</span> - the chosen variable supplies the
                rest of the URL.
              </p>
            </div>
          )}

          {selected && paramKeys.length === 0 && !selected.has_url_button && (
            <p className="text-xs text-muted-foreground">
              This template has no parameters - nothing to map.
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

'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Pencil, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  clearTemplateDefault,
  listTemplateDefaults,
  PARAM_VARIABLES,
  USE_CASES,
  type TemplateDefault,
  type UseCase,
} from '@/services/whatsappTemplateService';
import SetDefaultTemplateDialog from './SetDefaultTemplateDialog';

const variableLabel = (key: string) =>
  PARAM_VARIABLES.find((v) => v.key === key)?.label ?? key;

export default function TemplateDefaultsSection() {
  const queryClient = useQueryClient();
  const [editUseCase, setEditUseCase] = useState<UseCase | null>(null);
  const [clearing, setClearing] = useState<UseCase | null>(null);

  const { data: defaults, isLoading } = useQuery({
    queryKey: ['whatsapp-template-defaults'],
    queryFn: listTemplateDefaults,
  });

  const handleClear = async (useCase: UseCase) => {
    setClearing(useCase);
    try {
      await clearTemplateDefault(useCase);
      toast.success('Default template cleared');
      await queryClient.invalidateQueries({ queryKey: ['whatsapp-template-defaults'] });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to clear default');
    } finally {
      setClearing(null);
    }
  };

  const byUseCase = new Map<UseCase, TemplateDefault>(
    (defaults ?? []).map((d) => [d.use_case, d]),
  );

  const updateCases = USE_CASES.filter((u) => u.group !== 'chat');
  const chatCases = USE_CASES.filter((u) => u.group === 'chat');

  const renderRow = (useCase: (typeof USE_CASES)[number]) => {
    const current = byUseCase.get(useCase.key);
    const hasTemplate = Boolean(current?.template_id);
    const invalid = hasTemplate && current && !current.is_valid;
    return (
      <div
        key={useCase.key}
        className="flex items-center justify-between gap-4 py-3"
        data-testid={`default-row-${useCase.key}`}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm">{useCase.label}</span>
            {!hasTemplate && (
              <Badge variant="secondary" appearance="ghost">
                Not set
              </Badge>
            )}
            {invalid && (
              <Badge variant="destructive" appearance="ghost" className="gap-1">
                <AlertTriangle className="size-3" />
                Template no longer approved
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground truncate" title={useCase.description}>
            {useCase.description}
          </p>
          {hasTemplate && current && (
            <p className="text-xs mt-1">
              <span className="font-mono">{current.template_name}</span>
              {Object.keys(current.param_mapping).length > 0 && (
                <span className="text-muted-foreground">
                  {' · '}
                  {Object.entries(current.param_mapping)
                    .sort(([a], [b]) => Number(a) - Number(b))
                    .map(([n, v]) => `{{${n}}} → ${variableLabel(v)}`)
                    .join(', ')}
                </span>
              )}
            </p>
          )}
          {invalid && (
            <p className="text-xs text-destructive mt-1">
              Auto-sends for this use case are skipped until a valid template is set.
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button variant="outline" size="sm" onClick={() => setEditUseCase(useCase.key)}>
            <Pencil className="size-3.5 me-1" />
            {hasTemplate ? 'Change' : 'Set template'}
          </Button>
          {hasTemplate && (
            <Button
              variant="ghost"
              size="sm"
              disabled={clearing === useCase.key}
              onClick={() => handleClear(useCase.key)}
              aria-label={`Clear default for ${useCase.label}`}
            >
              <X className="size-3.5" />
            </Button>
          )}
        </div>
      </div>
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Default templates for auto-send</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {isLoading ? (
          <div className="space-y-2">
            {USE_CASES.map((u) => (
              <Skeleton key={u.key} className="h-14 w-full" />
            ))}
          </div>
        ) : (
          <>
            <div>
              <h4 className="text-sm font-semibold">Status update templates</h4>
              <p className="text-xs text-muted-foreground mb-1">
                When a contact&apos;s 24-hour WhatsApp window is closed, status updates are sent
                using the default template configured here instead of plain text.
              </p>
              <div className="divide-y">{updateCases.map(renderRow)}</div>
            </div>

            <div>
              <h4 className="text-sm font-semibold">Chat reply templates</h4>
              <p className="text-xs text-muted-foreground mb-1">
                When a contact&apos;s 24-hour window is closed and a staff member sends a free-text
                chat reply, it is delivered using the chat template for that form — carrying the
                sender&apos;s name and the typed message. Map a parameter to{' '}
                <span className="font-medium">Full update message</span> (required) and, ideally,{' '}
                <span className="font-medium">Sender name</span>.
              </p>
              <div className="divide-y">{chatCases.map(renderRow)}</div>
            </div>
          </>
        )}
      </CardContent>

      {editUseCase && (
        <SetDefaultTemplateDialog
          useCase={editUseCase}
          current={byUseCase.get(editUseCase) ?? null}
          open
          onOpenChange={(open) => {
            if (!open) setEditUseCase(null);
          }}
        />
      )}
    </Card>
  );
}

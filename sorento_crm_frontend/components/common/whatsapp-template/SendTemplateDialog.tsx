'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  listApprovedTemplates,
  renderTemplateBody,
  sendTemplateMessage,
  type WhatsAppTemplate,
} from '@/services/whatsappTemplateService';

interface SendTemplateDialogProps {
  entityType: string;
  entityId: string;
  contactId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after a successful send so the parent can refetch the chat list. */
  onSent?: () => void;
  /**
   * Intervention ticket this template answers. Passed to the backend so the
   * send stops THAT ticket's response clock; absent on every other surface.
   */
  trackingId?: string | null;
  /**
   * Overrides the send route. The default posts to the entity chat route keyed
   * by (entityType, entityId), which only exists for a real entity - the
   * Conversations inbox is keyed by CONTACT and has its own endpoint, so it
   * supplies one instead of the dialog being forked.
   */
  sendAdapter?: (input: {
    template_id: string;
    params: Record<string, string>;
  }) => Promise<unknown>;
}

/**
 * Manual WhatsApp template send - mimics Respond.io's flow:
 * pick an approved template → fill its positional params → live preview → send.
 */
export default function SendTemplateDialog({
  entityType,
  entityId,
  contactId,
  open,
  onOpenChange,
  onSent,
  trackingId = null,
  sendAdapter,
}: SendTemplateDialogProps) {
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [params, setParams] = useState<Record<string, string>>({});
  const [isSending, setIsSending] = useState(false);

  const { data: templates, isLoading } = useQuery({
    queryKey: ['whatsapp-templates', 'approved'],
    queryFn: listApprovedTemplates,
    enabled: open,
  });

  const filtered = useMemo(() => {
    const rows = templates ?? [];
    // Separator-insensitive search: template names use snake_case
    // (conversation_follow_up) but users type spaces. Normalize underscores /
    // hyphens / runs of whitespace to single spaces, then require every typed
    // token to appear - word order doesn't matter. Also match the fully-collapsed
    // form so "conversationfollowup" (no separators) still hits.
    const norm = (s: string) => s.toLowerCase().replace(/[\s_-]+/g, ' ').trim();
    const q = norm(search);
    if (!q) return rows;
    const tokens = q.split(' ');
    const qCollapsed = q.replace(/ /g, '');
    return rows.filter((t) => {
      const hay = norm(`${t.name} ${t.body_text}`);
      const hayCollapsed = hay.replace(/ /g, '');
      return tokens.every((tok) => hay.includes(tok)) || hayCollapsed.includes(qCollapsed);
    });
  }, [templates, search]);

  const selected: WhatsAppTemplate | null = useMemo(
    () => (templates ?? []).find((t) => t.id === selectedId) ?? null,
    [templates, selectedId],
  );

  const paramKeys = useMemo(
    () =>
      selected ? Array.from({ length: selected.param_count }, (_, i) => String(i + 1)) : [],
    [selected],
  );

  const allFilled = paramKeys.every((k) => (params[k] ?? '').trim());
  const canSend = Boolean(selected) && allFilled && !isSending;

  const handleSelect = (template: WhatsAppTemplate) => {
    setSelectedId(template.id);
    setParams({});
  };

  const resetAndClose = (nextOpen: boolean) => {
    if (!nextOpen) {
      setSearch('');
      setSelectedId(null);
      setParams({});
    }
    onOpenChange(nextOpen);
  };

  const handleSend = async () => {
    if (!selected) return;
    setIsSending(true);
    try {
      if (sendAdapter) {
        await sendAdapter({ template_id: selected.id, params });
      } else {
        await sendTemplateMessage(entityType, entityId, {
          contact_id: contactId,
          template_id: selected.id,
          params,
          tracking_id: trackingId,
        });
      }
      toast.success(`Template "${selected.name}" sent`);
      resetAndClose(false);
      onSent?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to send template');
    } finally {
      setIsSending(false);
    }
  };

  return (
    // `modal` is required: this dialog stacks ON TOP of the chat Sheet (itself a
    // modal Radix dialog whose react-remove-scroll lock blocks wheel/touch
    // everywhere except its own subtree). A non-modal dialog here is a portaled
    // sibling outside that lock - its inner scroll region scrolls programmatically
    // but eats every wheel/touch event. modal makes THIS dialog own the topmost
    // lock so its content becomes the scroll-allowed shard.
    <Dialog open={open} onOpenChange={resetAndClose} modal>
      <DialogContent className="sm:max-w-xl overflow-y-hidden">
        <DialogHeader className="shrink-0">
          <DialogTitle>Send WhatsApp template</DialogTitle>
          <DialogDescription>
            Templates are pre-approved by WhatsApp and can be sent even when the
            24-hour window is closed.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto">
          {!selected && (
            <>
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search templates..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="ps-9"
                />
              </div>
              {isLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                </div>
              ) : filtered.length === 0 ? (
                <p className="text-sm text-muted-foreground py-6 text-center">
                  No approved templates available. Sync templates from the
                  WhatsApp Templates page first.
                </p>
              ) : (
                <div className="space-y-2">
                  <div className="space-y-2">
                    {filtered.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => handleSelect(t)}
                        className={cn(
                          'w-full rounded-md border p-3 text-start transition-colors hover:bg-accent',
                        )}
                        data-testid={`template-option-${t.name}`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-xs font-medium">{t.name}</span>
                          <span className="text-xs text-muted-foreground">
                            {t.language} · {t.param_count} param{t.param_count === 1 ? '' : 's'}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                          {t.body_text}
                        </p>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {selected && (
            <>
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-sm font-medium">{selected.name}</span>
                <Button variant="ghost" size="sm" onClick={() => setSelectedId(null)}>
                  Change template
                </Button>
              </div>

              {paramKeys.length > 0 && (
                <div className="space-y-2">
                  <Label>Parameters</Label>
                  {paramKeys.map((key) => (
                    <div key={key} className="flex items-center gap-3">
                      <span className="font-mono text-sm w-12 shrink-0">{`{{${key}}}`}</span>
                      <Input
                        value={params[key] ?? ''}
                        onChange={(e) =>
                          setParams((prev) => ({ ...prev, [key]: e.target.value }))
                        }
                        placeholder={`Value for {{${key}}}`}
                      />
                    </div>
                  ))}
                </div>
              )}

              <div className="space-y-1">
                <Label>Preview</Label>
                <div className="rounded-lg bg-green-100 dark:bg-green-950 p-3 text-sm whitespace-pre-wrap">
                  {renderTemplateBody(selected.body_text, params)}
                </div>
              </div>
            </>
          )}
        </div>

        <DialogFooter className="shrink-0">
          <Button variant="outline" onClick={() => resetAndClose(false)} disabled={isSending}>
            Cancel
          </Button>
          <Button onClick={handleSend} disabled={!canSend}>
            {isSending ? 'Sending…' : 'Send template'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

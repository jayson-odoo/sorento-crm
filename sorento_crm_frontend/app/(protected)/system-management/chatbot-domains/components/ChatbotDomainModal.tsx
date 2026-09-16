'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoaderCircleIcon } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import StringChipInput from '@/components/common/StringChipInput';
import OrderableList from '@/components/common/OrderableList';
import RecordNavigation from '@/components/common/RecordNavigation';
import { listMcpToolsCatalog } from '@/app/(protected)/system-management/mcp-tools/services/mcpAdminService';
import { getChatbotDomainPromptBlock } from '../services/chatbotDomainService';
import { useChatbotEntityKindsQuery } from '@/app/(protected)/system-management/chatbot-entity-kinds/hooks/useChatbotEntityKinds';
import {
  useChatbotDomainDeletion,
  useCreateChatbotDomain,
  useUpdateChatbotDomain,
} from '../hooks/useChatbotDomains';
import {
  NARROWING_POLICY_OPTIONS,
  SUGGESTED_TEAM_OPTIONS,
  type ChatbotDomain,
  type ChatbotDomainInput,
  type NarrowingPolicy,
} from '../types/chatbotDomain.types';

const BLANK: ChatbotDomainInput = {
  name: '',
  label: '',
  intents: [],
  tools: [],
  primary_tool: null,
  escalation_team_code: null,
  switch_words: [],
  narrowing: {},
  takes_date_filter: false,
  // No control edits this. `Profile.grants` stays unrestricted in APPLY and the
  // per-domain reveal gate is still the lanes' (S3 ruling, 16 Sep 2026), so a value
  // set here would change nothing and read as a switch that does not work. The
  // trigger for bringing the control back is wiring `Profile.grants` to
  // `chatbot_domains.reveal_key` in `turn_runtime.load_profile`. An existing row's
  // key is carried through a save untouched (the draft is a copy of the row).
  reveal_key: null,
  supported: true,
  ladder: [],
};

export interface ChatbotDomainModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Null = create. */
  domainId: string | null;
  /** The list's current (filtered) rows - the neighbours prev/next walks (AttachmentDetailModal
   * precedent: a modal that steps through the SET the reader is looking at, not a server order). */
  rows: ChatbotDomain[];
  onNavigate: (id: string) => void;
  /** `system.chatbot_config.manage`. Without it the modal reads the row and nothing more:
   * no Save, no Delete, every field disabled. The backend enforces the same slug. */
  canManage: boolean;
}

export default function ChatbotDomainModal({
  open,
  onOpenChange,
  domainId,
  rows,
  onNavigate,
  canManage,
}: ChatbotDomainModalProps) {
  const isNew = domainId === null;
  const current = domainId ? rows.find((r) => r.id === domainId) : null;

  const [draft, setDraft] = useState<ChatbotDomainInput>(BLANK);
  const [tab, setTab] = useState('general');

  useEffect(() => {
    if (!open) return;
    setDraft(current ? { ...current } : BLANK);
    setTab('general');
    // Re-derive only when the modal opens on a different record - `rows` changes on
    // every keystroke in the list's search box and must not reset an in-progress edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, domainId]);

  const set = <K extends keyof ChatbotDomainInput>(key: K, value: ChatbotDomainInput[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }));

  const { data: mcpTools } = useQuery({
    queryKey: ['mcp-tools-catalog'],
    queryFn: () => listMcpToolsCatalog(),
  });
  const { data: entityKinds } = useChatbotEntityKindsQuery();

  const create = useCreateChatbotDomain();
  const update = useUpdateChatbotDomain();
  const deletion = useChatbotDomainDeletion();
  const saving = create.isPending || update.isPending;

  const modalIndex = domainId ? rows.findIndex((r) => r.id === domainId) : -1;

  const otherDomainOptions = useMemo(
    () => rows.filter((r) => r.name !== draft.name).map((r) => ({ value: r.name, label: r.label })),
    [rows, draft.name],
  );
  const domainLabelByName = useMemo(
    () => new Map(rows.map((r) => [r.name, r.label])),
    [rows],
  );

  const handleSave = () => {
    if (!draft.name.trim() || !draft.label.trim()) return;
    if (isNew) {
      create.mutate(draft, { onSuccess: () => onOpenChange(false) });
    } else if (domainId) {
      update.mutate({ id: domainId, input: draft }, { onSuccess: () => onOpenChange(false) });
    }
  };

  const handleDelete = () => {
    if (!current) return;
    deletion.run({ id: current.id, subject: current.label });
    onOpenChange(false);
  };

  // The block comes from the backend, which renders it with the same function the
  // publish uses - so what this tab shows and what the parser is told are one sentence,
  // not two that drift. It reads the SAVED row: an unsaved edit has not reached the
  // prompt yet, and a domain that does not exist has no paragraph at all.
  const { data: promptBlock, isLoading: promptBlockLoading } = useQuery({
    queryKey: ['chatbot-domain-prompt-block', domainId],
    queryFn: () => getChatbotDomainPromptBlock(domainId as string),
    enabled: open && tab === 'prompt' && Boolean(domainId),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90dvh] max-w-2xl flex-col overflow-hidden p-0">
        <DialogHeader className="flex-row items-center justify-between gap-4 border-b px-6 py-4 pr-12">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-muted-foreground">Chatbot Domains</p>
            <DialogTitle className="truncate">
              {isNew ? 'Add domain' : (current?.name ?? 'Domain')}
            </DialogTitle>
          </div>
          {!isNew && rows.length > 1 && (
            <RecordNavigation
              index={modalIndex + 1}
              total={rows.length}
              hasPrevious={modalIndex > 0}
              hasNext={modalIndex >= 0 && modalIndex < rows.length - 1}
              onPrevious={() => onNavigate(rows[modalIndex - 1].id)}
              onNext={() => onNavigate(rows[modalIndex + 1].id)}
              ariaLabel="domain"
            />
          )}
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          <fieldset disabled={!canManage} className="m-0 min-w-0 border-0 p-0">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="general">General</TabsTrigger>
              <TabsTrigger value="narrowing">Narrowing</TabsTrigger>
              <TabsTrigger value="ladder">Ladder</TabsTrigger>
              <TabsTrigger value="prompt">Prompt block</TabsTrigger>
            </TabsList>

            <TabsContent value="general" className="mt-4 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="domain-name">Name</Label>
                <Input
                  id="domain-name"
                  value={draft.name}
                  onChange={(e) => set('name', e.target.value)}
                  placeholder="incoming"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="domain-label">Label (customer sees)</Label>
                <Input
                  id="domain-label"
                  value={draft.label}
                  onChange={(e) => set('label', e.target.value)}
                  placeholder="Incoming"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Intents</Label>
                <StringChipInput
                  value={draft.intents}
                  onChange={(v) => set('intents', v)}
                  placeholder="check_incoming"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Tools (from the MCP tools list)</Label>
                <SearchableMultiSelect
                  value={draft.tools}
                  onChange={(v) => {
                    set('tools', v);
                    if (draft.primary_tool && !v.includes(draft.primary_tool)) {
                      set('primary_tool', null);
                    }
                  }}
                  options={(mcpTools ?? []).map((t) => ({ value: t.tool_name, label: t.tool_name }))}
                  placeholder="Add a tool..."
                  emptyMessage="No MCP tool found."
                />
              </div>
              <div className="space-y-1.5">
                <Label>Primary tool</Label>
                <SearchableSelect
                  value={draft.primary_tool ?? ''}
                  onChange={(v) => set('primary_tool', v || null)}
                  clearable
                  placeholder="(none)"
                  options={draft.tools.map((t) => ({ value: t, label: t }))}
                  emptyMessage="Add a tool above first."
                />
              </div>
              <div className="space-y-1.5">
                <Label>Escalation team</Label>
                <SearchableSelect
                  value={draft.escalation_team_code ?? ''}
                  onChange={(v) => set('escalation_team_code', v || null)}
                  clearable
                  placeholder="(none)"
                  options={SUGGESTED_TEAM_OPTIONS}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Switch words</Label>
                <StringChipInput
                  value={draft.switch_words}
                  onChange={(v) => set('switch_words', v)}
                  placeholder="incoming, eta, container"
                />
              </div>
              <div className="flex items-center justify-between gap-4">
                <Label htmlFor="domain-date-filter" className="cursor-pointer font-normal">
                  Takes a date filter
                </Label>
                <Switch
                  id="domain-date-filter"
                  checked={draft.takes_date_filter}
                  onCheckedChange={(v) => set('takes_date_filter', v === true)}
                />
              </div>
              <div className="flex items-center justify-between gap-4">
                <Label htmlFor="domain-supported" className="cursor-pointer font-normal">
                  Supported
                </Label>
                <Switch
                  id="domain-supported"
                  checked={draft.supported}
                  onCheckedChange={(v) => set('supported', v === true)}
                />
              </div>
            </TabsContent>

            <TabsContent value="narrowing" className="mt-4 space-y-3">
              <p className="text-sm text-muted-foreground">
                Per entity kind present under this domain: what the reader must narrow before
                the answer can fetch.
              </p>
              {(entityKinds ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No entity kind is defined yet.</p>
              ) : (
                <div className="space-y-2">
                  {(entityKinds ?? []).map((kind) => {
                    const policy = draft.narrowing[kind.code] ?? 'not_applicable';
                    return (
                      <div
                        key={kind.code}
                        className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
                      >
                        <span className="text-sm font-medium">{kind.label}</span>
                        <SearchableSelect
                          value={policy}
                          onChange={(v) =>
                            set('narrowing', {
                              ...draft.narrowing,
                              [kind.code]: v as NarrowingPolicy,
                            })
                          }
                          triggerClassName="w-56"
                          options={NARROWING_POLICY_OPTIONS.map((o) => ({
                            value: o.value,
                            label: o.label,
                          }))}
                        />
                      </div>
                    );
                  })}
                </div>
              )}
            </TabsContent>

            <TabsContent value="ladder" className="mt-4 space-y-3">
              <p className="text-sm text-muted-foreground">
                When this domain&apos;s answer is zero or short, climb in this order.
              </p>
              <OrderableList
                items={draft.ladder}
                labelFor={(name) => domainLabelByName.get(name) ?? name}
                onChange={(v) => set('ladder', v)}
                onRemove={(name) => set('ladder', draft.ladder.filter((n) => n !== name))}
              />
              <SearchableSelect
                value=""
                onChange={(v) => {
                  if (!v || draft.ladder.includes(v)) return;
                  set('ladder', [...draft.ladder, v]);
                }}
                placeholder="Add a rung..."
                options={otherDomainOptions.filter((o) => !draft.ladder.includes(o.value))}
                emptyMessage="No other domain to add."
              />
            </TabsContent>

            <TabsContent value="prompt" className="mt-4 space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Prompt block
              </p>
              {promptBlockLoading ? (
                <Skeleton className="h-16 w-full" />
              ) : promptBlock ? (
                <pre className="whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">
                  {promptBlock}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {isNew ? 'Save the domain to see its block.' : 'No block rendered yet.'}
                </p>
              )}
            </TabsContent>
          </Tabs>
          </fieldset>
        </div>

        <div className="flex items-center justify-between gap-3 border-t px-6 py-4">
          <div>
            {!isNew && canManage && (
              <Button type="button" variant="ghost" className="text-destructive" onClick={handleDelete}>
                Delete
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {canManage ? 'Cancel' : 'Close'}
            </Button>
            {canManage && (
              <Button
                type="button"
                onClick={handleSave}
                disabled={saving || !draft.name.trim() || !draft.label.trim()}
              >
                {saving && <LoaderCircleIcon className="size-4 animate-spin" />}
                Save
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

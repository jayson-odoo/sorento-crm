'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Bell,
  ExternalLink,
  Eye,
  GitBranch,
  Link2,
  ListChecks,
  Plus,
  Rocket,
  Save,
  Trash2,
  Workflow,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { toast } from 'sonner';
import {
  usePublishWorkflowDefinition,
  useUpdateWorkflowDefinition,
  useWorkflowDefinitionQuery,
  useWorkflowFlowGraphQuery,
} from '../hooks/useWorkflowForms';
import type {
  WorkflowFieldType,
  WorkflowFormSchema,
  WorkflowHeaderField,
  WorkflowLineGroup,
  WorkflowNotificationRule,
  WorkflowState,
  WorkflowTransition,
} from '../types/workflowForms.types';
import RoleIdsPicker from './RoleIdsPicker';
import { WorkflowHeaderFieldsForm } from './WorkflowDynamicFields';
import { FIELD_TYPES, fieldUsesChoices } from './workflow-field-constants';
import { WorkflowFieldChoicesEditor } from './workflow-field-choices-editor';
import { WorkflowHeaderSectionsEditor } from './WorkflowHeaderSectionsEditor';
import { emptyHeaderSections, flattenHeaderFields, normalizeWorkflowFormSchema } from '../utils/workflowFormSchema';
import { getOrigin, workflowNewBlankUrl } from '../utils/workflowShareLinks';

function emptySchema(): WorkflowFormSchema {
  return {
    header_sections: emptyHeaderSections(),
    header_fields: [],
    line_groups: [],
    states: [],
    transitions: [],
    notification_rules: [],
  };
}

export default function WorkflowFormBuilder({ definitionId }: { definitionId: string }) {
  const { data: def, isLoading } = useWorkflowDefinitionQuery(definitionId);
  const updateMut = useUpdateWorkflowDefinition(definitionId);
  const publishMut = usePublishWorkflowDefinition(definitionId);
  const { data: flowDraft } = useWorkflowFlowGraphQuery(definitionId, 'draft');
  const { data: flowPublished } = useWorkflowFlowGraphQuery(
    definitionId,
    'published',
    !!def?.published_version_id,
  );

  const [schema, setSchema] = useState<WorkflowFormSchema>(emptySchema());
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [previewHeaderData, setPreviewHeaderData] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (!def) return;
    setName(def.name);
    setDescription(def.description ?? '');
    setIsActive(def.is_active);
    const ds = def.draft_schema as WorkflowFormSchema;
    setSchema(
      normalizeWorkflowFormSchema(
        ds && typeof ds === 'object'
          ? {
              header_fields: ds.header_fields ?? [],
              header_sections: ds.header_sections,
              line_groups: ds.line_groups ?? [],
              states: ds.states ?? [],
              transitions: ds.transitions ?? [],
              notification_rules: ds.notification_rules ?? [],
            }
          : emptySchema(),
      ),
    );
  }, [def]);

  const saveMeta = () => {
    updateMut.mutate({ name, description: description || null, is_active: isActive });
  };

  const saveSchema = () => {
    updateMut.mutate({
      draft_schema: {
        ...schema,
        header_fields: flattenHeaderFields(schema),
      },
    });
  };

  const addHeaderSection = () => {
    const id = `sec_${crypto.randomUUID().slice(0, 8)}`;
    setSchema((s) => {
      const base = s.header_sections?.length ? s.header_sections : emptyHeaderSections();
      const next = [...base, { id, title: 'New section', fields: [] as WorkflowHeaderField[] }];
      return { ...s, header_sections: next, header_fields: next.flatMap((x) => x.fields) };
    });
  };

  const addLineGroup = () => {
    const id = `lg_${crypto.randomUUID().slice(0, 8)}`;
    const g: WorkflowLineGroup = { id, name: 'Line items', fields: [] };
    setSchema((s) => ({ ...s, line_groups: [...s.line_groups, g] }));
  };

  const addLineField = (gi: number) => {
    const id = `lf_${crypto.randomUUID().slice(0, 8)}`;
    const f: WorkflowHeaderField = { id, type: 'text', label: 'Column', required: false };
    setSchema((s) => {
      const groups = [...s.line_groups];
      groups[gi] = { ...groups[gi], fields: [...groups[gi].fields, f] };
      return { ...s, line_groups: groups };
    });
  };

  const updateLineField = (gi: number, fi: number, patch: Partial<WorkflowHeaderField>) => {
    setSchema((s) => {
      const groups = [...s.line_groups];
      const fields = [...groups[gi].fields];
      fields[fi] = { ...fields[fi], ...patch };
      groups[gi] = { ...groups[gi], fields };
      return { ...s, line_groups: groups };
    });
  };

  const removeLineField = (gi: number, fi: number) => {
    setSchema((s) => {
      const groups = [...s.line_groups];
      groups[gi] = {
        ...groups[gi],
        fields: groups[gi].fields.filter((_, i) => i !== fi),
      };
      return { ...s, line_groups: groups };
    });
  };

  const removeLineGroup = (gi: number) => {
    setSchema((s) => ({ ...s, line_groups: s.line_groups.filter((_, i) => i !== gi) }));
  };

  const addState = () => {
    const id = `s_${crypto.randomUUID().slice(0, 8)}`;
    const st: WorkflowState = {
      id,
      name: 'State',
      code: `state_${schema.states.length + 1}`,
      is_initial: false,
      is_terminal: false,
      view_role_ids: [],
      edit_role_ids: [],
    };
    setSchema((s) => ({ ...s, states: [...s.states, st] }));
  };

  const updateState = (idx: number, patch: Partial<WorkflowState>) => {
    setSchema((s) => {
      const next = [...s.states];
      next[idx] = { ...next[idx], ...patch };
      return { ...s, states: next };
    });
  };

  const removeState = (idx: number) => {
    setSchema((s) => ({ ...s, states: s.states.filter((_, i) => i !== idx) }));
  };

  const addTransition = () => {
    const from = schema.states[0]?.id ?? '';
    const to = schema.states[1]?.id ?? from;
    const t: WorkflowTransition = {
      id: `tr_${crypto.randomUUID().slice(0, 8)}`,
      from_state_id: from,
      to_state_id: to,
      label: 'Move',
      direction: 'forward',
      allowed_role_ids: [],
    };
    setSchema((s) => ({ ...s, transitions: [...s.transitions, t] }));
  };

  const updateTransition = (idx: number, patch: Partial<WorkflowTransition>) => {
    setSchema((s) => {
      const next = [...s.transitions];
      next[idx] = { ...next[idx], ...patch };
      return { ...s, transitions: next };
    });
  };

  const removeTransition = (idx: number) => {
    setSchema((s) => ({ ...s, transitions: s.transitions.filter((_, i) => i !== idx) }));
  };

  const addNotificationRule = () => {
    const tid = schema.transitions[0]?.id ?? '';
    const r: WorkflowNotificationRule = {
      transition_id: tid,
      channels: ['in_app'],
      recipient_role_ids: [],
    };
    setSchema((s) => ({ ...s, notification_rules: [...s.notification_rules, r] }));
  };

  const updateNotificationRule = (idx: number, patch: Partial<WorkflowNotificationRule>) => {
    setSchema((s) => {
      const next = [...s.notification_rules];
      next[idx] = { ...next[idx], ...patch };
      return { ...s, notification_rules: next };
    });
  };

  const removeNotificationRule = (idx: number) => {
    setSchema((s) => ({
      ...s,
      notification_rules: s.notification_rules.filter((_, i) => i !== idx),
    }));
  };

  const flowBlock = useMemo(() => {
    const render = (
      title: string,
      flow: typeof flowDraft,
    ) => (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {!flow ? (
            <p className="text-muted-foreground">No data</p>
          ) : (
            <>
              <div>
                <p className="font-medium mb-1">States</p>
                <ul className="list-disc ms-4 space-y-1">
                  {flow.nodes.map((n) => (
                    <li key={n.id}>
                      {n.name} ({n.code})
                      {n.is_initial ? ' - initial' : ''}
                      {n.is_terminal ? ' - terminal' : ''}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="font-medium mb-1">Transitions</p>
                <ul className="list-disc ms-4 space-y-1">
                  {flow.edges.map((e) => (
                    <li key={e.id}>
                      {e.label}: {e.from_state_id} → {e.to_state_id} ({e.direction})
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    );
    return (
      <div className="grid gap-4 md:grid-cols-2">
        {render('Draft flow', flowDraft)}
        {render('Published flow', flowPublished)}
      </div>
    );
  }, [flowDraft, flowPublished]);

  if (isLoading || !def) {
    return <p className="p-6 text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/workflow-forms-management/definitions">
            <ArrowLeft className="size-4 mr-1" />
            Back
          </Link>
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            saveMeta();
          }}
          disabled={updateMut.isPending}
        >
          Save settings
        </Button>
        <Button size="sm" onClick={() => saveSchema()} disabled={updateMut.isPending}>
          <Save className="size-4 mr-1" />
          Save draft schema
        </Button>
        <Button
          size="sm"
          variant="primary"
          onClick={() => publishMut.mutate()}
          disabled={publishMut.isPending || updateMut.isPending}
        >
          <Rocket className="size-4 mr-1" />
          Publish version
        </Button>
        {def.published_version_number != null ? (
          <span className="text-sm text-muted-foreground">
            Published: v{def.published_version_number}
          </span>
        ) : (
          <span className="text-sm text-amber-600">Not published yet - submissions require publish.</span>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={def.published_version_id == null}
              title={
                def.published_version_id == null
                  ? 'Publish the form first'
                  : 'Copy or open link for a new submission (sign-in required)'
              }
            >
              <Link2 className="size-4 mr-1" />
              Share link
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem
              onClick={() => {
                const o = getOrigin();
                if (!o) return;
                const url = workflowNewBlankUrl(o, definitionId);
                void navigator.clipboard
                  .writeText(url)
                  .then(() => toast.success('Link copied'))
                  .catch(() => toast.error('Could not copy'));
              }}
            >
              <Link2 className="size-4 mr-2" />
              Copy work link (new submission)
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => {
                const o = getOrigin();
                if (!o) return;
                window.open(workflowNewBlankUrl(o, definitionId), '_blank', 'noopener,noreferrer');
              }}
            >
              <ExternalLink className="size-4 mr-2" />
              Open in new tab
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Code</Label>
            <Input value={def.code} disabled />
          </div>
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Description</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={isActive} onCheckedChange={setIsActive} id="active" />
            <Label htmlFor="active">Active</Label>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="form">
        {/* Wrapping the pills doubled the strip's height on a phone and still
            cut the last label; the line strip scrolls on one row instead. */}
        <TabsList className="mb-4">
          <TabsTrigger value="form">
            <ListChecks />
            <span>Form fields</span>
          </TabsTrigger>
          <TabsTrigger value="workflow">
            <Workflow />
            <span>States &amp; transitions</span>
          </TabsTrigger>
          <TabsTrigger value="notify">
            <Bell />
            <span>Notifications</span>
          </TabsTrigger>
          <TabsTrigger value="preview">
            <Eye />
            <span>Preview</span>
          </TabsTrigger>
          <TabsTrigger value="flow">
            <GitBranch />
            <span>Flow view</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="form" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Header fields</CardTitle>
              <p className="text-sm text-muted-foreground font-normal">
                Organize fields into sections. Drag using the grip handles to reorder or move fields between sections.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              <WorkflowHeaderSectionsEditor
                sections={schema.header_sections ?? emptyHeaderSections()}
                onChange={(next) =>
                  setSchema((s) => ({
                    ...s,
                    header_sections: next,
                    header_fields: next.flatMap((x) => x.fields),
                  }))
                }
                onAddSection={addHeaderSection}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Line groups</CardTitle>
              <Button size="sm" variant="outline" onClick={addLineGroup}>
                <Plus className="size-4 mr-1" />
                Add group
              </Button>
            </CardHeader>
            <CardContent className="space-y-6">
              {schema.line_groups.map((g, gi) => (
                <div key={`line-group-${gi}`} className="border rounded-md p-4 space-y-3">
                  <div className="flex flex-wrap gap-2 items-end">
                    <div className="flex-1 min-w-[120px] space-y-1">
                      <Label className="text-xs">Group id</Label>
                      <Input
                        value={g.id}
                        onChange={(e) => {
                          const id = e.target.value;
                          setSchema((s) => {
                            const groups = [...s.line_groups];
                            groups[gi] = { ...groups[gi], id };
                            return { ...s, line_groups: groups };
                          });
                        }}
                      />
                    </div>
                    <div className="flex-1 min-w-[120px] space-y-1">
                      <Label className="text-xs">Name</Label>
                      <Input
                        value={g.name}
                        onChange={(e) => {
                          const name = e.target.value;
                          setSchema((s) => {
                            const groups = [...s.line_groups];
                            groups[gi] = { ...groups[gi], name };
                            return { ...s, line_groups: groups };
                          });
                        }}
                      />
                    </div>
                    <Button size="sm" variant="outline" onClick={() => addLineField(gi)}>
                      <Plus className="size-4 mr-1" />
                      Column
                    </Button>
                    <Button size="icon" variant="ghost" onClick={() => removeLineGroup(gi)}>
                      <Trash2 className="size-4 text-destructive" />
                    </Button>
                  </div>
                  {g.fields.map((f, fi) => (
                    <div key={`line-field-${gi}-${fi}`} className="grid gap-2 md:grid-cols-6 border rounded p-2 ms-2">
                      <div className="md:col-span-2 space-y-1">
                        <Label className="text-xs">Id</Label>
                        <Input
                          value={f.id}
                          onChange={(e) => updateLineField(gi, fi, { id: e.target.value })}
                        />
                      </div>
                      <div className="md:col-span-2 space-y-1">
                        <Label className="text-xs">Label</Label>
                        <Input
                          value={f.label}
                          onChange={(e) => updateLineField(gi, fi, { label: e.target.value })}
                        />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Type</Label>
                        <SearchableSelect
                          value={f.type}
                          onChange={(v) => {
                            const t = v as WorkflowFieldType;
                            const patch: Partial<WorkflowHeaderField> = { type: t };
                            if (fieldUsesChoices(t)) {
                              if (!f.options?.length) {
                                patch.options = [{ value: 'choice_1', label: 'Choice 1' }];
                              }
                            } else {
                              patch.options = undefined;
                            }
                            updateLineField(gi, fi, patch);
                          }}
                          options={FIELD_TYPES.map((t) => ({ value: t, label: t }))}
                        />
                      </div>
                      <div className="flex items-end justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <Checkbox
                            id={`req-l-${gi}-${fi}`}
                            checked={!!f.required}
                            onCheckedChange={(c) => updateLineField(gi, fi, { required: c === true })}
                          />
                          <Label htmlFor={`req-l-${gi}-${fi}`} className="text-xs">
                            Req
                          </Label>
                        </div>
                        <Button size="icon" variant="ghost" onClick={() => removeLineField(gi, fi)}>
                          <Trash2 className="size-4 text-destructive" />
                        </Button>
                      </div>
                      {fieldUsesChoices(f.type) ? (
                        <WorkflowFieldChoicesEditor
                          options={f.options ?? []}
                          onChange={(next) => updateLineField(gi, fi, { options: next })}
                        />
                      ) : null}
                    </div>
                  ))}
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="workflow" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">States</CardTitle>
              <Button size="sm" variant="outline" onClick={addState}>
                <Plus className="size-4 mr-1" />
                Add state
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {schema.states.map((st, idx) => (
                <div key={`workflow-state-${idx}`} className="grid gap-2 md:grid-cols-12 border rounded-md p-3">
                  <div className="md:col-span-3 space-y-1">
                    <Label className="text-xs">Id</Label>
                    <Input value={st.id} onChange={(e) => updateState(idx, { id: e.target.value })} />
                  </div>
                  <div className="md:col-span-2 space-y-1">
                    <Label className="text-xs">Code</Label>
                    <Input value={st.code} onChange={(e) => updateState(idx, { code: e.target.value })} />
                  </div>
                  <div className="md:col-span-3 space-y-1">
                    <Label className="text-xs">Name</Label>
                    <Input value={st.name} onChange={(e) => updateState(idx, { name: e.target.value })} />
                  </div>
                  <div className="flex items-center gap-2 md:col-span-2">
                    <Checkbox
                      id={`ini-${idx}`}
                      checked={!!st.is_initial}
                      onCheckedChange={(c) => updateState(idx, { is_initial: c === true })}
                    />
                    <Label htmlFor={`ini-${idx}`} className="text-xs">
                      Initial
                    </Label>
                  </div>
                  <div className="flex items-center gap-2 md:col-span-1">
                    <Checkbox
                      id={`term-${idx}`}
                      checked={!!st.is_terminal}
                      onCheckedChange={(c) => updateState(idx, { is_terminal: c === true })}
                    />
                    <Label htmlFor={`term-${idx}`} className="text-xs">
                      Terminal
                    </Label>
                  </div>
                  <div className="md:col-span-12 grid md:grid-cols-2 gap-4">
                    <RoleIdsPicker
                      label="View (empty = any viewer with submission permission)"
                      value={st.view_role_ids ?? []}
                      onChange={(ids) => updateState(idx, { view_role_ids: ids })}
                    />
                    <RoleIdsPicker
                      label="Edit (empty = any editor)"
                      value={st.edit_role_ids ?? []}
                      onChange={(ids) => updateState(idx, { edit_role_ids: ids })}
                    />
                  </div>
                  <div className="md:col-span-12 flex justify-end">
                    <Button size="icon" variant="ghost" onClick={() => removeState(idx)}>
                      <Trash2 className="size-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Transitions</CardTitle>
              <Button size="sm" variant="outline" onClick={addTransition} disabled={schema.states.length < 2}>
                <Plus className="size-4 mr-1" />
                Add transition
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {schema.transitions.map((t, idx) => (
                <div key={`workflow-transition-${idx}`} className="grid gap-2 md:grid-cols-12 border rounded-md p-3">
                  <div className="md:col-span-3 space-y-1">
                    <Label className="text-xs">Id</Label>
                    <Input value={t.id} onChange={(e) => updateTransition(idx, { id: e.target.value })} />
                  </div>
                  <div className="md:col-span-2 space-y-1">
                    <Label className="text-xs">Label</Label>
                    <Input value={t.label} onChange={(e) => updateTransition(idx, { label: e.target.value })} />
                  </div>
                  <div className="md:col-span-2 space-y-1">
                    <Label className="text-xs">From state</Label>
                    <SearchableSelect
                      value={t.from_state_id}
                      onChange={(v) => updateTransition(idx, { from_state_id: v })}
                      options={schema.states.map((s) => ({ value: s.id, label: `${s.name} (${s.code})` }))}
                    />
                  </div>
                  <div className="md:col-span-2 space-y-1">
                    <Label className="text-xs">To state</Label>
                    <SearchableSelect
                      value={t.to_state_id}
                      onChange={(v) => updateTransition(idx, { to_state_id: v })}
                      options={schema.states.map((s) => ({ value: s.id, label: `${s.name} (${s.code})` }))}
                    />
                  </div>
                  <div className="md:col-span-2 space-y-1">
                    <Label className="text-xs">Direction</Label>
                    <SearchableSelect
                      value={t.direction}
                      onChange={(v) => updateTransition(idx, { direction: v as 'forward' | 'back' })}
                      options={[
                        { value: 'forward', label: 'forward' },
                        { value: 'back', label: 'back' },
                      ]}
                    />
                  </div>
                  <div className="md:col-span-12">
                    <RoleIdsPicker
                      label="Who can use this transition (empty = any user with transition permission)"
                      value={t.allowed_role_ids ?? []}
                      onChange={(ids) => updateTransition(idx, { allowed_role_ids: ids })}
                    />
                  </div>
                  <div className="md:col-span-12 flex justify-end">
                    <Button size="icon" variant="ghost" onClick={() => removeTransition(idx)}>
                      <Trash2 className="size-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notify" className="mt-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Notification rules</CardTitle>
              <Button size="sm" variant="outline" onClick={addNotificationRule} disabled={!schema.transitions.length}>
                <Plus className="size-4 mr-1" />
                Add rule
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {schema.notification_rules.map((r, idx) => (
                <div key={idx} className="border rounded-md p-3 space-y-3">
                  <div className="grid gap-2 md:grid-cols-2">
                    <div className="space-y-1">
                      <Label className="text-xs">When transition</Label>
                      <SearchableSelect
                        value={r.transition_id}
                        onChange={(v) => updateNotificationRule(idx, { transition_id: v })}
                        options={schema.transitions.map((t) => ({ value: t.id, label: `${t.label} (${t.id})` }))}
                        placeholder="Select transition"
                      />
                    </div>
                    <div className="flex flex-wrap gap-4 items-center">
                      <div className="flex items-center gap-2">
                        <Checkbox
                          id={`ch-in-${idx}`}
                          checked={r.channels.includes('in_app')}
                          onCheckedChange={(c) => {
                            const ch = new Set(r.channels);
                            if (c === true) ch.add('in_app');
                            else ch.delete('in_app');
                            updateNotificationRule(idx, { channels: Array.from(ch) as ('in_app' | 'email')[] });
                          }}
                        />
                        <Label htmlFor={`ch-in-${idx}`}>In-app</Label>
                      </div>
                      <div className="flex items-center gap-2">
                        <Checkbox
                          id={`ch-em-${idx}`}
                          checked={r.channels.includes('email')}
                          onCheckedChange={(c) => {
                            const ch = new Set(r.channels);
                            if (c === true) ch.add('email');
                            else ch.delete('email');
                            updateNotificationRule(idx, { channels: Array.from(ch) as ('in_app' | 'email')[] });
                          }}
                        />
                        <Label htmlFor={`ch-em-${idx}`}>Email</Label>
                      </div>
                    </div>
                  </div>
                  <RoleIdsPicker
                    label="Notify users having these roles"
                    value={r.recipient_role_ids}
                    onChange={(ids) => updateNotificationRule(idx, { recipient_role_ids: ids })}
                  />
                  <div className="flex justify-end">
                    <Button size="icon" variant="ghost" onClick={() => removeNotificationRule(idx)}>
                      <Trash2 className="size-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="preview" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Form preview (draft)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <WorkflowHeaderFieldsForm
                schema={schema}
                data={previewHeaderData}
                onChange={setPreviewHeaderData}
              />
              {schema.line_groups.map((g) => (
                <div key={g.id} className="border rounded-md p-3 space-y-2">
                  <p className="font-medium">{g.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {g.fields.length} column(s) - users add rows at runtime.
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="flow" className="mt-4">
          {flowBlock}
        </TabsContent>
      </Tabs>
    </div>
  );
}

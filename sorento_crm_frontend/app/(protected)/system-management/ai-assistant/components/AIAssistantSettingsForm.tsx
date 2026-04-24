'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import { useAIAssistantConfig, useAIAssistantTools, useUpdateAIAssistantConfig } from '../hooks/useAIAssistantAdmin';

export default function AIAssistantSettingsForm() {
  const { data, isLoading, isError, error } = useAIAssistantConfig();
  const toolsQuery = useAIAssistantTools();
  const updateCfg = useUpdateAIAssistantConfig();

  const [provider, setProvider] = useState('openai');
  const [model, setModel] = useState('gpt-4o-mini');
  const [temperature, setTemperature] = useState(0);
  const [systemPrompt, setSystemPrompt] = useState('');
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [apiKeyEdited, setApiKeyEdited] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [toolSearch, setToolSearch] = useState('');
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [ragEnabled, setRagEnabled] = useState(true);
  const [isEnabled, setIsEnabled] = useState(true);

  useEffect(() => {
    if (!data) return;
    setProvider(data.provider || 'openai');
    setModel(data.model || 'gpt-4o-mini');
    setTemperature(data.temperature ?? 0);
    setSystemPrompt(data.system_prompt || '');
    setEnabledTools(data.enabled_tools || []);
    setRagEnabled(!!data.rag_enabled);
    setIsEnabled(!!data.is_enabled);
    setApiKeyInput(data.api_key_masked || '');
    setApiKeyEdited(false);
  }, [data]);

  const filteredTools = useMemo(() => {
    const allTools = toolsQuery.data || [];
    const q = toolSearch.trim().toLowerCase();
    if (!q) return allTools;
    return allTools.filter((t) => t.toLowerCase().includes(q));
  }, [toolSearch, toolsQuery.data]);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Loading...
      </div>
    );
  }
  if (isError) return <p className="text-sm text-destructive">{(error as Error)?.message || 'Failed to load config'}</p>;

  return (
    <div className="space-y-4 rounded-md border p-4">
      <div className="grid gap-3 md:grid-cols-3">
        <div className="space-y-2">
          <Label>Provider</Label>
          <Input value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="openai" />
        </div>
        <div className="space-y-2">
          <Label>Model</Label>
          <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o-mini" />
        </div>
        <div className="space-y-2">
          <Label>Temperature (0-2)</Label>
          <Input
            type="number"
            min={0}
            max={2}
            step={1}
            value={temperature}
            onChange={(e) => setTemperature(Number(e.target.value || 0))}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label>System prompt</Label>
        <p className="text-xs text-muted-foreground">
          Use the toolbar to format the prompt. Formatting is stripped to plain text before being sent to
          the LLM, so what you see here is just for readability. Leave blank to use the built-in default.
        </p>
        <RichTextEditor
          value={systemPrompt}
          onChange={setSystemPrompt}
          minHeight={280}
          placeholder="Describe the assistant's role, rules, and form-collection choreography..."
        />
      </div>

      <div className="space-y-2">
        <Label>API key</Label>
        <Input
          type="text"
          value={apiKeyInput}
          onChange={(e) => {
            setApiKeyInput(e.target.value);
            setApiKeyEdited(true);
          }}
          placeholder="****1234"
        />
      </div>

      <div className="space-y-2">
        <Label>Enabled tools</Label>
        {toolsQuery.isError ? (
          <p className="text-xs text-destructive">
            {(toolsQuery.error as Error)?.message || 'Failed to load MCP tools'}
          </p>
        ) : null}
        <Popover open={toolsOpen} onOpenChange={setToolsOpen}>
          <PopoverTrigger asChild>
            <Button type="button" variant="outline" className="w-full justify-between">
              <span>{enabledTools.length ? `${enabledTools.length} tool(s) selected` : 'Select tools'}</span>
              <ChevronDown className="size-4" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[360px] p-3" align="start">
            <div className="space-y-3">
              <Input
                value={toolSearch}
                onChange={(e) => setToolSearch(e.target.value)}
                placeholder="Search tools..."
                disabled={toolsQuery.isLoading}
              />
              <div className="flex items-center justify-between gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setEnabledTools(Array.from(new Set([...enabledTools, ...filteredTools])))}
                  disabled={toolsQuery.isLoading}
                >
                  Select all
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setEnabledTools((prev) => prev.filter((x) => !filteredTools.includes(x)))}
                  disabled={toolsQuery.isLoading}
                >
                  Clear all
                </Button>
              </div>
            </div>
            <div className="mt-3 max-h-56 space-y-2 overflow-y-auto">
              {toolsQuery.isLoading ? (
                <p className="text-xs text-muted-foreground">Loading MCP tools...</p>
              ) : null}
              {filteredTools.map((t) => (
                <label key={t} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={enabledTools.includes(t)}
                    onCheckedChange={(checked) =>
                      setEnabledTools((prev) =>
                        checked ? Array.from(new Set([...prev, t])) : prev.filter((x) => x !== t),
                      )
                    }
                  />
                  {t}
                </label>
              ))}
              {!toolsQuery.isLoading && filteredTools.length === 0 ? (
                <p className="text-xs text-muted-foreground">No tools found</p>
              ) : null}
            </div>
          </PopoverContent>
        </Popover>
        <div className="flex flex-wrap gap-2">
          {enabledTools.length === 0 ? (
            <span className="text-xs text-muted-foreground">No tools selected</span>
          ) : (
            enabledTools.map((tool) => (
              <Badge key={tool} variant="secondary" className="font-mono text-xs">
                {tool}
              </Badge>
            ))
          )}
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <Checkbox checked={ragEnabled} onCheckedChange={(c) => setRagEnabled(c === true)} />
        Enable RAG tool selection
      </label>

      <label className="flex items-center gap-2 text-sm">
        <Checkbox checked={isEnabled} onCheckedChange={(c) => setIsEnabled(c === true)} />
        Assistant enabled
      </label>

      <Button
        type="button"
        disabled={updateCfg.isPending}
        onClick={() => {
          updateCfg.mutate(
            {
              provider: provider.trim(),
              model: model.trim(),
              temperature,
              system_prompt: systemPrompt,
              api_key: apiKeyEdited ? apiKeyInput.trim() || undefined : undefined,
              enabled_tools: enabledTools,
              rag_enabled: ragEnabled,
              is_enabled: isEnabled,
            },
            {
              onSuccess: (saved) => {
                toast.success('AI assistant settings saved');
                setApiKeyInput(saved.api_key_masked || '');
                setApiKeyEdited(false);
              },
              onError: (e: Error) => toast.error(e.message),
            },
          );
        }}
      >
        {updateCfg.isPending ? <Loader2 className="size-4 animate-spin" /> : 'Save settings'}
      </Button>
    </div>
  );
}

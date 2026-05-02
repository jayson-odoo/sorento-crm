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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider, SliderThumb } from '@/components/ui/slider';
import {
  useAIAssistantConfig,
  useAIAssistantTools,
  useTestAIAssistantConnection,
  useUpdateAIAssistantConfig,
} from '../hooks/useAIAssistantAdmin';

const PROVIDER_OPTIONS: { value: string; label: string }[] = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
];

const MODEL_OPTIONS: Record<string, { value: string; label: string }[]> = {
  openai: [
    { value: 'gpt-4o-mini', label: 'GPT-4o mini' },
    { value: 'gpt-4o', label: 'GPT-4o' },
    { value: 'gpt-4.1', label: 'GPT-4.1' },
  ],
  anthropic: [
    { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5' },
    { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
    { value: 'claude-opus-4-7', label: 'Claude Opus 4.7' },
  ],
};

export default function AIAssistantSettingsForm() {
  const { data, isLoading, isError, error } = useAIAssistantConfig();
  const toolsQuery = useAIAssistantTools();
  const updateCfg = useUpdateAIAssistantConfig();
  const testConn = useTestAIAssistantConnection();

  const [provider, setProvider] = useState('openai');
  const [model, setModel] = useState('gpt-4o-mini');
  const [customModel, setCustomModel] = useState(false);
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
    const loadedProvider = data.provider || 'openai';
    const loadedModel = data.model || 'gpt-4o-mini';
    setProvider(loadedProvider);
    setModel(loadedModel);
    // Auto-detect custom-model if loaded model isn't in the standard list for the provider.
    const knownForProvider = (MODEL_OPTIONS[loadedProvider] || []).some((m) => m.value === loadedModel);
    setCustomModel(!knownForProvider);
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

  const modelOptions = MODEL_OPTIONS[provider] || [];

  const handleProviderChange = (next: string) => {
    setProvider(next);
    // Reset model to first option in the new provider's list (unless user has chosen custom).
    if (!customModel) {
      const first = MODEL_OPTIONS[next]?.[0]?.value;
      if (first) setModel(first);
    }
  };

  const handleTestConnection = () => {
    if (!apiKeyEdited || !apiKeyInput.trim()) {
      toast.error('Enter API key to test');
      return;
    }
    testConn.mutate(
      { provider: provider.trim(), api_key: apiKeyInput.trim(), model: model.trim() },
      {
        onSuccess: (result) => {
          if (result.ok) {
            toast.success(`Connected in ${result.latency_ms}ms via ${provider}`);
          } else {
            toast.error(result.message || 'Connection failed');
          }
        },
        onError: (e: Error) => toast.error(e.message),
      },
    );
  };

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
          <Select value={provider} onValueChange={handleProviderChange}>
            <SelectTrigger>
              <SelectValue placeholder="Select provider" />
            </SelectTrigger>
            <SelectContent>
              {PROVIDER_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Model</Label>
          {customModel ? (
            <Input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="custom-model-name"
            />
          ) : (
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger>
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                {modelOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <Checkbox
              checked={customModel}
              onCheckedChange={(c) => setCustomModel(c === true)}
            />
            Custom model
          </label>
        </div>
        <div className="space-y-2">
          <Label>Temperature: {temperature.toFixed(1)}</Label>
          <div className="px-1 pt-3">
            <Slider
              min={0}
              max={2}
              step={0.1}
              value={[temperature]}
              onValueChange={(vals: number[]) => {
                const v = vals?.[0];
                if (typeof v === 'number') setTemperature(v);
              }}
            >
              <SliderThumb />
            </Slider>
          </div>
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
        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={testConn.isPending}
            onClick={handleTestConnection}
          >
            {testConn.isPending ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Testing...
              </>
            ) : (
              'Test connection'
            )}
          </Button>
          {!apiKeyEdited ? (
            <span className="text-xs text-muted-foreground">Enter API key to test</span>
          ) : null}
        </div>
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

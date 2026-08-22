'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ExternalLink, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Slider, SliderThumb } from '@/components/ui/slider';
import {
  useAIAssistantConfig,
  useAIAssistantTools,
  useTestAIAssistantConnection,
  useUpdateAIAssistantConfig,
} from '../hooks/useAIAssistantAdmin';
import { MODEL_OPTIONS, PROVIDER_OPTIONS } from '../lib/modelOptions';
import { useProviderModels } from '@/hooks/useProviderModels';


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
  // Dedicated Anthropic key — used by the SCM market-research web search (Anthropic-only)
  // while the assistant itself can run on the primary provider above.
  const [anthropicKeyInput, setAnthropicKeyInput] = useState('');
  const [anthropicKeyEdited, setAnthropicKeyEdited] = useState(false);
  // Dedicated Gemini key - the chatbot media image lane can run on Gemini while
  // the assistant itself stays on the primary provider above.
  const [geminiKeyInput, setGeminiKeyInput] = useState('');
  const [geminiKeyEdited, setGeminiKeyEdited] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [toolSearch, setToolSearch] = useState('');
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [ragEnabled, setRagEnabled] = useState(true);
  const [isEnabled, setIsEnabled] = useState(true);
  const modelsQuery = useProviderModels(provider);

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
    setAnthropicKeyInput(data.anthropic_api_key_masked || '');
    setAnthropicKeyEdited(false);
    setGeminiKeyInput(data.gemini_api_key_masked || '');
    setGeminiKeyEdited(false);
  }, [data]);

  const filteredTools = useMemo(() => {
    const allTools = toolsQuery.data || [];
    const q = toolSearch.trim().toLowerCase();
    if (!q) return allTools;
    return allTools.filter((t) => t.toLowerCase().includes(q));
  }, [toolSearch, toolsQuery.data]);

  // The provider's own catalogue, with the built-in table standing in only while
  // it cannot be reached: a hand-maintained list goes stale without saying so, and
  // a retired model stays on offer until someone hits it.
  const modelOptions = modelsQuery.data?.models ?? MODEL_OPTIONS[provider] ?? [];

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
          <SearchableSelect
            value={provider}
            onChange={handleProviderChange}
            options={PROVIDER_OPTIONS.map((opt) => ({ value: opt.value, label: opt.label }))}
            placeholder="Select provider"
          />
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
            <SearchableSelect
              value={model}
              onChange={setModel}
              options={modelOptions.map((opt) => ({ value: opt.value, label: opt.label }))}
              placeholder="Select model"
            />
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

      <div className="space-y-2 rounded-md border border-dashed p-3">
        <Label>System prompt</Label>
        <p className="text-xs text-muted-foreground">
          The system prompt now lives in the versioned prompt registry as{' '}
          <span className="font-mono">agent_system</span> — editable, diffable, and publishable without a
          redeploy. This field is deprecated.
        </p>
        <Button asChild variant="outline" size="sm">
          <Link href="/system-management/ai-assistant/prompts/agent_system" data-testid="agent-system-link">
            Edit in Prompts → agent_system
            <ExternalLink className="size-4" />
          </Link>
        </Button>
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
        <Label>Anthropic API key</Label>
        <p className="text-xs text-muted-foreground">
          Used by SCM market-research web search (Anthropic-only). Leave blank if unused.
        </p>
        <Input
          type="text"
          value={anthropicKeyInput}
          onChange={(e) => {
            setAnthropicKeyInput(e.target.value);
            setAnthropicKeyEdited(true);
          }}
          placeholder="sk-ant-****"
        />
      </div>

      <div className="space-y-2">
        <Label>Google Gemini API key</Label>
        <p className="text-xs text-muted-foreground">
          Used when a lane runs on Gemini (chatbot media image reading). Leave blank if unused.
        </p>
        <Input
          type="text"
          value={geminiKeyInput}
          onChange={(e) => {
            setGeminiKeyInput(e.target.value);
            setGeminiKeyEdited(true);
          }}
          placeholder="AIza****"
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
              anthropic_api_key: anthropicKeyEdited
                ? anthropicKeyInput.trim() || undefined
                : undefined,
              gemini_api_key: geminiKeyEdited ? geminiKeyInput.trim() || undefined : undefined,
              enabled_tools: enabledTools,
              rag_enabled: ragEnabled,
              is_enabled: isEnabled,
            },
            {
              onSuccess: (saved) => {
                toast.success('AI assistant settings saved');
                setApiKeyInput(saved.api_key_masked || '');
                setApiKeyEdited(false);
                setAnthropicKeyInput(saved.anthropic_api_key_masked || '');
                setAnthropicKeyEdited(false);
                setGeminiKeyInput(saved.gemini_api_key_masked || '');
                setGeminiKeyEdited(false);
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

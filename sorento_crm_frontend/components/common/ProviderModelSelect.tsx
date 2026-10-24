'use client';

import { useState } from 'react';

import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useProviderModels } from '@/hooks/useProviderModels';
import {
  MODEL_OPTIONS,
  PROVIDER_OPTIONS,
} from '@/app/(protected)/system-management/ai-assistant/lib/modelOptions';

export type ProviderModel = { provider: string; model: string };

/**
 * The model list is asked of the provider, so it only exists once a provider is chosen. Its own
 * component so the request is made for the chosen provider alone.
 */
function ModelPick({
  provider,
  model,
  disabled,
  onPick,
}: {
  provider: string;
  model: string;
  disabled?: boolean;
  onPick: (model: string) => void;
}) {
  const modelsQuery = useProviderModels(provider);
  const options = modelsQuery.data?.models ?? MODEL_OPTIONS[provider] ?? [];
  return (
    <SearchableSelect
      value={model}
      onChange={onPick}
      options={options}
      placeholder="Select a model"
      disabled={disabled}
      clearable
      createOption={{ label: (q) => `Use "${q}"`, onCreate: onPick }}
    />
  );
}

/**
 * A provider + model pair. A provider picked without a model stays local: `onChange` only ever
 * receives a complete pair, or null once the provider is cleared.
 */
export function ProviderModelSelect({
  value,
  onChange,
  disabled,
}: {
  value: ProviderModel | null;
  onChange: (next: ProviderModel | null) => void;
  disabled?: boolean;
}) {
  const [pendingProvider, setPendingProvider] = useState('');
  const provider = pendingProvider || value?.provider || '';
  const model = pendingProvider ? '' : (value?.model ?? '');

  const pickProvider = (next: string) => {
    setPendingProvider(next);
    if (!next && value) onChange(null);
  };
  const pickModel = (next: string) => {
    const trimmed = next.trim();
    if (!trimmed) {
      setPendingProvider(provider);
      if (value) onChange(null);
      return;
    }
    setPendingProvider('');
    onChange({ provider, model: trimmed });
  };

  return (
    <div className="flex flex-wrap gap-2">
      <div className="min-w-40 flex-1">
        <SearchableSelect
          value={provider}
          onChange={pickProvider}
          options={PROVIDER_OPTIONS}
          placeholder="Default"
          disabled={disabled}
          clearable
        />
      </div>
      {provider ? (
        <div className="min-w-40 flex-1">
          <ModelPick provider={provider} model={model} disabled={disabled} onPick={pickModel} />
        </div>
      ) : null}
    </div>
  );
}

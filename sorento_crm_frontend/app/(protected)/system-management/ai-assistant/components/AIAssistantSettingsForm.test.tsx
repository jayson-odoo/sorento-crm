/**
 * AIAssistantSettingsForm - the three provider API key fields (OpenAI/primary,
 * Anthropic, Gemini) share one behaviour contract:
 *
 * - a saved key renders MASKED (the value the backend returns, e.g. "****1234")
 * - typing in the field marks it "edited"; the save payload then carries the
 *     new value the operator typed
 * - a field the operator never touched sends nothing (undefined), so a save
 *     never overwrites a working key with a stale masked placeholder
 *
 * Data hooks are mocked at the module boundary; nothing hits the network.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import AIAssistantSettingsForm from './AIAssistantSettingsForm';

const CONFIG = {
  id: 'cfg-1',
  provider: 'openai',
  model: 'gpt-4o-mini',
  temperature: 0,
  system_prompt: '',
  api_key_masked: '****1234',
  anthropic_api_key_masked: '****2222',
  gemini_api_key_masked: '****3333',
  enabled_tools: [],
  rag_enabled: true,
  is_enabled: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mutateConfig = vi.fn();
const mutateTestConn = vi.fn();

vi.mock('../hooks/useAIAssistantAdmin', () => ({
  useAIAssistantConfig: () => ({ data: CONFIG, isLoading: false, isError: false, error: null }),
  useAIAssistantTools: () => ({ data: [], isLoading: false, isError: false, error: null }),
  useUpdateAIAssistantConfig: () => ({ mutate: mutateConfig, isPending: false }),
  useTestAIAssistantConnection: () => ({ mutate: mutateTestConn, isPending: false }),
}));

// The model dropdown now asks the provider for its catalogue, so the hook is
// stubbed here the same way the admin hooks are - this file renders the form
// without a QueryClientProvider on purpose.
vi.mock('@/hooks/useProviderModels', () => ({
  useProviderModels: () => ({
    data: { provider: 'openai', source: 'live', message: null, models: [] },
  }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeEach(() => {
  mutateConfig.mockClear();
  mutateTestConn.mockClear();
});
afterEach(() => cleanup());

function save() {
  fireEvent.click(screen.getByRole('button', { name: /save settings/i }));
}

function lastPayload() {
  expect(mutateConfig).toHaveBeenCalledTimes(1);
  return mutateConfig.mock.calls[0][0];
}

describe('AIAssistantSettingsForm - API key fields', () => {
  it('renders each saved key masked', () => {
    render(<AIAssistantSettingsForm />);
    expect(screen.getByPlaceholderText('****1234')).toHaveValue('****1234');
    expect(screen.getByPlaceholderText('sk-ant-****')).toHaveValue('****2222');
    expect(screen.getByPlaceholderText('AIza****')).toHaveValue('****3333');
  });

  it('sends nothing for an untouched key on save', () => {
    render(<AIAssistantSettingsForm />);
    save();
    const payload = lastPayload();
    expect(payload.api_key).toBeUndefined();
    expect(payload.anthropic_api_key).toBeUndefined();
    expect(payload.gemini_api_key).toBeUndefined();
  });

  it('marks the primary key edited and carries the new value on save', () => {
    render(<AIAssistantSettingsForm />);
    fireEvent.change(screen.getByPlaceholderText('****1234'), {
      target: { value: 'sk-new-primary-key' },
    });
    save();
    const payload = lastPayload();
    expect(payload.api_key).toBe('sk-new-primary-key');
    expect(payload.anthropic_api_key).toBeUndefined();
    expect(payload.gemini_api_key).toBeUndefined();
  });

  it('marks the Anthropic key edited and carries the new value on save', () => {
    render(<AIAssistantSettingsForm />);
    fireEvent.change(screen.getByPlaceholderText('sk-ant-****'), {
      target: { value: 'sk-ant-new-key' },
    });
    save();
    const payload = lastPayload();
    expect(payload.anthropic_api_key).toBe('sk-ant-new-key');
    expect(payload.api_key).toBeUndefined();
    expect(payload.gemini_api_key).toBeUndefined();
  });

  it('marks the Gemini key edited and carries the new value on save', () => {
    render(<AIAssistantSettingsForm />);
    fireEvent.change(screen.getByPlaceholderText('AIza****'), {
      target: { value: 'test-not-a-real-key' },
    });
    save();
    const payload = lastPayload();
    expect(payload.gemini_api_key).toBe('test-not-a-real-key');
    expect(payload.api_key).toBeUndefined();
    expect(payload.anthropic_api_key).toBeUndefined();
  });
});

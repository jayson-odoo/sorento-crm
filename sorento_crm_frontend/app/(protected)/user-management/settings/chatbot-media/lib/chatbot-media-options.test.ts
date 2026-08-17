import { describe, expect, it } from 'vitest';
import { imageModelOptions } from './chatbot-media-options';
import { MODEL_OPTIONS } from '@/app/(protected)/system-management/ai-assistant/lib/modelOptions';

describe('imageModelOptions', () => {
  it('returns a provider-specific list, ungrouped, when a provider is chosen', () => {
    expect(imageModelOptions('gemini')).toEqual(MODEL_OPTIONS.gemini);
    expect(imageModelOptions('openai')).toEqual(MODEL_OPTIONS.openai);
    expect(imageModelOptions('anthropic')).toEqual(MODEL_OPTIONS.anthropic);
  });

  it('groups every model under its provider label when no provider is chosen', () => {
    const options = imageModelOptions('');

    const openaiOption = options.find((o) => o.value === 'gpt-4o-mini');
    expect(openaiOption?.group).toBe('OpenAI');

    const anthropicOption = options.find((o) => o.value === 'claude-haiku-4-5');
    expect(anthropicOption?.group).toBe('Anthropic');

    const geminiOption = options.find((o) => o.value === 'gemini-2.5-flash');
    expect(geminiOption?.group).toBe('Google Gemini');

    // Every model from every provider is present, not just a subset.
    const totalModels = Object.values(MODEL_OPTIONS).reduce((n, list) => n + list.length, 0);
    expect(options).toHaveLength(totalModels);
  });
});

import { describe, expect, it } from 'vitest';
import { parseCsv, toCsv } from './chatbot-media-options';

/**
 * The image model list used to be tested here. It has moved out of the frontend
 * entirely - the page asks the provider through `useProviderModels` - because a
 * hardcoded slice both went stale (Google retired `gemini-2.5-flash-lite` while
 * it was still on offer in that list) and, with no provider chosen, mixed every
 * provider's ids into one list a Gemini id could be picked from and saved
 * against an OpenAI key.
 *
 * What is left here is the language-hint CSV pair, which is still this page's.
 */

describe('language hint CSV', () => {
  it('reads a hint list, ignoring spacing and empty entries', () => {
    expect(parseCsv(' en , ms ,, zh ')).toEqual(['en', 'ms', 'zh']);
  });

  it('treats a missing value as no hints rather than one empty hint', () => {
    expect(parseCsv(null)).toEqual([]);
    expect(parseCsv(undefined)).toEqual([]);
    expect(parseCsv('')).toEqual([]);
  });

  it('writes back without duplicating a language', () => {
    expect(toCsv(['en', 'ms', 'en'])).toBe('en,ms');
  });
});

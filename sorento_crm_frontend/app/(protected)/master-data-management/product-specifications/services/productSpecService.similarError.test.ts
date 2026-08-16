/**
 * The near-duplicate 422 is a TOP-LEVEL body, not the AppException envelope, so every
 * write that can provoke it has to parse the body itself. `updateSpecKey` is one of
 * them: the PATCH guard fires on any payload carrying `user_values`, and the master
 * registry editor always sends that field.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import {
  addValueToSpecKey,
  createSpecKey,
  updateSpecKey,
  SpecSimilarError,
} from './productSpecService';

const mockedFetch = vi.mocked(apiFetch);

const SIMILAR_BODY = {
  error: '"Matte Black" is already black on Finish.',
  match: {
    spec_key: 'finish',
    label: 'Finish',
    matched_on: 'synonym',
    matched_text: 'black',
  },
  acknowledge_field: 'acknowledge_similar',
};

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => vi.clearAllMocks());

describe('the near-duplicate 422 reaches the caller as itself', () => {
  it('updateSpecKey throws SpecSimilarError naming the colliding word', async () => {
    mockedFetch.mockResolvedValue(jsonResponse(SIMILAR_BODY, 422));

    const thrown = await updateSpecKey('finish', { user_values: ['Matte Black'] }).catch(
      (e) => e as Error,
    );

    expect(thrown).toBeInstanceOf(SpecSimilarError);
    expect(thrown.message).toBe('"Matte Black" is already black on Finish.');
    expect((thrown as SpecSimilarError).match).toMatchObject({
      spec_key: 'finish',
      matched_text: 'black',
    });
  });

  it.each([
    ['createSpecKey', () => createSpecKey({ spec_key: 'finish2', label: 'Finish or colour', data_type: 'text' })],
    ['addValueToSpecKey', () => addValueToSpecKey('finish', ['Matte Black'])],
  ])('%s throws it too, so the three writes behave alike', async (_name, call) => {
    mockedFetch.mockResolvedValue(jsonResponse(SIMILAR_BODY, 422));

    const thrown = await call().catch((e) => e as Error);

    expect(thrown).toBeInstanceOf(SpecSimilarError);
    expect(thrown.message).toBe('"Matte Black" is already black on Finish.');
  });

  it('updateSpecKey still reports an ordinary failure as a plain error', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ detail: 'A seeded key cannot change its allowed values.' }, 400),
    );

    const thrown = await updateSpecKey('finish', { allowed_values: ['chrome'] }).catch(
      (e) => e as Error,
    );

    expect(thrown).not.toBeInstanceOf(SpecSimilarError);
    expect(thrown.message).toBe('A seeded key cannot change its allowed values.');
  });

  it('updateSpecKey falls back to its own message when a 422 carries no match', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({}, 422));

    const thrown = await updateSpecKey('finish', { rank_weight: 2 }).catch((e) => e as Error);

    expect(thrown).not.toBeInstanceOf(SpecSimilarError);
    expect(thrown.message).toBe('Failed to save the spec key');
  });

  it('returns the saved key when the server accepts it', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({ spec_key: 'finish', label: 'Finish' }, 200));

    await expect(updateSpecKey('finish', { user_values: ['brushed brass'] })).resolves.toMatchObject(
      { spec_key: 'finish' },
    );
  });
});

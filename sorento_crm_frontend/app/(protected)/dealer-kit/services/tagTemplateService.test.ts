/**
 * Tag template service - `print_size` carried alongside `doc` (S1, PLAN D1,
 * AC-S1-3).
 *
 * Before this round `updateTemplate` sent `{ doc }` only, so `print_size`
 * never changed even though the template editor now lets a user resize the
 * tag: the PUT body is asserted here rather than trusting the type checker,
 * since a body that silently drops a field is exactly the kind of thing that
 * compiles fine and ships broken (see `LESSONS-LEARNT.md` on
 * `response_model` dropping undeclared fields - the same shape of bug, on
 * the request side). `printSizeOf(doc)` is the one helper both `createTemplate`
 * and `updateTemplate` read the size from, so the two paths cannot ever state
 * two different sizes for the same doc.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { createTemplate, updateTemplate } from './tagTemplateService';
import type { TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';

const mockFetch = vi.mocked(apiFetch);

function ok(body: unknown) {
  return { ok: true, json: async () => body } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('updateTemplate (S1, AC-S1-3)', () => {
  it('sends print_size equal to the doc\'s own width_mm/height_mm', async () => {
    mockFetch.mockResolvedValue(ok({ id: 't1' }));
    const doc: TagTemplateDoc = { width_mm: 85, height_mm: 58, layers: [] };

    await updateTemplate('t1', doc);

    const [, init] = mockFetch.mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.print_size).toEqual({ width_mm: 85, height_mm: 58 });
    expect(body.doc).toEqual(doc);
  });

  it('a resized doc changes the PUT body\'s print_size to match, not the size the template was created at', async () => {
    mockFetch.mockResolvedValue(ok({ id: 't1' }));
    const resized: TagTemplateDoc = { width_mm: 100, height_mm: 62, layers: [] };

    await updateTemplate('t1', resized);

    const [, init] = mockFetch.mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.print_size).toEqual({ width_mm: 100, height_mm: 62 });
  });

  it('carries the keepalive flag through for the page-teardown flush', async () => {
    mockFetch.mockResolvedValue(ok({ id: 't1' }));
    const doc: TagTemplateDoc = { width_mm: 85, height_mm: 58, layers: [] };

    await updateTemplate('t1', doc, { keepalive: true });

    const [, init] = mockFetch.mock.calls[0];
    expect((init as RequestInit).keepalive).toBe(true);
  });
});

describe('createTemplate (S1)', () => {
  it('derives print_size from the SAME doc it builds, not a second, separate value', async () => {
    mockFetch.mockResolvedValue(ok({ id: 't1' }));

    await createTemplate({
      name: 'DIY Tag',
      family: 'ala_carte',
      print_size: { width_mm: 60, height_mm: 40 },
    });

    const [, init] = mockFetch.mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.print_size).toEqual({ width_mm: 60, height_mm: 40 });
    expect(body.doc).toMatchObject({ width_mm: 60, height_mm: 40, layers: [] });
  });
});

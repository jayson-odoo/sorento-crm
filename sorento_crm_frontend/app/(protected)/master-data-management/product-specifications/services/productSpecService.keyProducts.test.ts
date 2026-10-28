/** FILTER-MULTISELECT PR4: `getSpecKeyProducts` sends Value and Class arrays as repeated params, each item
 * whole, so a value or class label containing a comma reaches the server unsplit. */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { getSpecKeyProducts } from './productSpecService';

const mockedFetch = vi.mocked(apiFetch);

function sentQuery(): URLSearchParams {
  const url = String(mockedFetch.mock.calls[0][0]);
  return new URLSearchParams(url.split('?')[1]);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedFetch.mockResolvedValue(new Response(JSON.stringify({ products: [] }), { status: 200 }));
});

describe('getSpecKeyProducts - repeated params', () => {
  it('Value items with a comma reach the request whole, one param each', async () => {
    await getSpecKeyProducts('finish', { value: ['["Gold", "Matt Black"]', 'Chrome'] });
    expect(sentQuery().getAll('value')).toEqual(['["Gold", "Matt Black"]', 'Chrome']);
  });

  it('Class items with a comma reach the request whole, one param each', async () => {
    await getSpecKeyProducts('finish', { classLabel: ['Sink, Undermount', 'Tap'] });
    expect(sentQuery().getAll('class_label')).toEqual(['Sink, Undermount', 'Tap']);
  });

  it('no Value or Class sends neither param', async () => {
    await getSpecKeyProducts('finish', { q: 'x' });
    expect(sentQuery().has('value')).toBe(false);
    expect(sentQuery().has('class_label')).toBe(false);
    expect(sentQuery().get('q')).toBe('x');
  });
});

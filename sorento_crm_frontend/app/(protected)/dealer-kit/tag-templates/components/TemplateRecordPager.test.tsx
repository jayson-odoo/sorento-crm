/**
 * TAG-TEMPLATE-DUPLICATE item 2 (owner 6 Nov): the template editor's prev/next walks the Tag
 * Templates list the reader came from, in the SAME order and with the SAME filters and search,
 * read back off the editor URL (the list's row link writes them there).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const nav = vi.hoisted(() => ({ search: '', push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
  usePathname: () => '/dealer-kit/tag-templates/b',
}));
vi.mock('@/hooks/usePrefetchOnce', () => ({ usePrefetchOnce: () => () => {} }));

const listTemplates = vi.hoisted(() => vi.fn());
vi.mock('../../services/tagTemplateService', () => ({
  listTemplates: (...a: unknown[]) => listTemplates(...a),
}));

import { TemplateRecordPager } from './TemplateRecordPager';

const row = (id: string) => ({ id, name: id });

function draw(id: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TemplateRecordPager id={id} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  nav.push.mockReset();
  listTemplates.mockReset();
});

describe('TemplateRecordPager', () => {
  it('asks for the list with the sort, search and filters the editor URL carries', async () => {
    nav.search = 'page=1&limit=50&sort=name&dir=desc&query=BF&price_type=list,unset&family=toilet&status=live';
    listTemplates.mockResolvedValue([row('a'), row('b'), row('c')]);
    draw('b');

    await waitFor(() => expect(listTemplates).toHaveBeenCalled());
    expect(listTemplates.mock.calls[0][0]).toEqual({
      price_type: 'list,unset',
      family: 'toilet',
      status: 'live',
      query: 'BF',
      sort: 'name',
      dir: 'desc',
    });
  });

  it('counts N / M in the server order and steps keep the filters and sort on the URL', async () => {
    nav.search = 'page=1&limit=50&sort=name&dir=desc&price_type=list';
    listTemplates.mockResolvedValue([row('c'), row('b'), row('a')]);
    draw('b');

    expect(await screen.findByText('2 / 3')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next template' }));

    expect(nav.push).toHaveBeenCalledTimes(1);
    const href = String(nav.push.mock.calls[0][0]);
    expect(href.startsWith('/dealer-kit/tag-templates/a?')).toBe(true);
    const params = new URLSearchParams(href.split('?')[1]);
    expect(params.get('sort')).toBe('name');
    expect(params.get('dir')).toBe('desc');
    expect(params.get('price_type')).toBe('list');
  });

  it('with no sort walks the manual order the server answers', async () => {
    nav.search = 'page=1&limit=50';
    listTemplates.mockResolvedValue([row('x'), row('b'), row('y')]);
    draw('b');

    expect(await screen.findByText('2 / 3')).toBeInTheDocument();
    expect(listTemplates.mock.calls[0][0].sort).toBeUndefined();
    fireEvent.click(screen.getByRole('button', { name: 'Previous template' }));
    expect(String(nav.push.mock.calls[0][0]).startsWith('/dealer-kit/tag-templates/x?')).toBe(true);
  });
});

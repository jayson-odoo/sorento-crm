/** LOOKUP-EMBED-CENTRAL review fix round 5, K-1..K-3: header and grid layout contracts (jsdom has no layout, so structural). */
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';

import { GEM, M3S, lookupWords, overview } from './embeddingsStubs';

const gridProps: { columns?: Array<{ id?: string; size?: number }> } = {};
vi.mock('@/components/common/PanelDataGrid', () => ({
  PanelDataGrid: (props: { columns: Array<{ id?: string; size?: number }> }) => {
    gridProps.columns = props.columns;
    return <div data-testid="grid" />;
  },
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

import { EmbeddingsHeader } from '../components/EmbeddingsHeader';
import { LookupWordsGrid } from '../components/LookupWordsGrid';

afterEach(() => cleanup());

const NO_CLIP = /(^|\s)(truncate|text-ellipsis|whitespace-nowrap)(\s|$)/;
const renderHeader = (mode: 'lookup' | 'records' = 'lookup') =>
  render(
    <EmbeddingsHeader
      overview={{ ...overview, guard: { ...overview.guard, running: false } } as never}
      loading={false}
      mode={mode}
      onEmbedMissing={vi.fn()}
      embedPending={false}
      onStartBackfill={vi.fn()}
      backfillPending={false}
    />,
  );

describe('K-1 record search reads cell', () => {
  it('keeps the model text and the in-progress badge in separate elements inside a wrapping or stacked parent', () => {
    renderHeader();
    const badge = screen.getByText(`${GEM} in progress`);
    const modelEl = screen.getByText(M3S);
    expect(modelEl.contains(badge)).toBe(false);
    expect(modelEl).not.toBe(badge);
    let shared: HTMLElement | null = modelEl.parentElement;
    while (shared && !shared.contains(badge)) shared = shared.parentElement;
    expect(shared).toBeTruthy();
    const cls = shared!.className;
    expect(cls).toMatch(/flex-wrap|flex-col/);
    expect(cls).not.toMatch(NO_CLIP);
  });
});

describe('K-2 header stats do not clip', () => {
  it('has no truncating class on a stat label or value without the full text in a title', () => {
    const { container } = renderHeader();
    for (const text of ['Embedder', 'Lookup words with a vector', 'Record chunks, new model', 'Record search reads']) {
      const label = screen.getByText(text);
      const metric = label.parentElement!;
      for (const el of [label, ...Array.from(metric.children)] as HTMLElement[]) {
        if (NO_CLIP.test(el.className)) {
          const title = el.getAttribute('title') ?? '';
          expect(title.length, `${text}: truncating element needs a title`).toBeGreaterThan(0);
          expect(title).toContain((el.textContent ?? '').trim());
        }
      }
    }
    const embedder = within(screen.getByText('Embedder').parentElement!).getAllByText(GEM)[0];
    expect(embedder.className).not.toMatch(NO_CLIP);
    expect(container.querySelector('.grid')).toBeTruthy();
  });
});

describe('K-3 Vectors column', () => {
  it('has an explicit size wide enough for the n / m badge', () => {
    render(<LookupWordsGrid rows={lookupWords.rows as never} isLoading={false} />);
    const vectors = gridProps.columns!.find((c) => c.id === 'vectors')!;
    expect(vectors.size).toBeGreaterThanOrEqual(120);
  });
});

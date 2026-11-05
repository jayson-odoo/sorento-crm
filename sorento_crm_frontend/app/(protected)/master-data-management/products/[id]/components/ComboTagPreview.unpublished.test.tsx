/**
 * PRICETAG-COMBO-FORMAT fix round 1, R12: the live tag preview tells apart "no default template
 * linked" from "the default template exists but is not published", which reads
 * "No published price tag template".
 *
 * Written test-FIRST: both cases read "No price tag template linked" today.
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  default: (props: { payload: unknown }) => <div data-testid="design-viewer">{props.payload ? 'drawn' : 'empty'}</div>,
}));

const state = vi.hoisted(() => ({ links: [] as unknown[], published: [] as unknown[] }));
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  useComboTagTemplates: () => ({ data: state.links, isLoading: false, isError: false }),
}));
vi.mock('@/app/(protected)/dealer-kit/hooks/usePublishedTagTemplates', () => ({
  usePublishedTagTemplates: () => ({ data: state.published, isLoading: false, isError: false }),
}));

import { ComboTagPreview } from './ComboTagPreview';

const combo = {
  id: 'combo-3',
  host_product_id: 'prod-1',
  name: '3 in 1',
  sort_order: 0,
  parts: [],
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
};

const link = {
  id: 'tpl-sp',
  name: 'Bathroom Furniture SP',
  family: 'ala_carte',
  published: false,
  width_mm: 85,
  height_mm: 58,
  price_type: 'selling',
  is_default: true,
  default_list: true,
  default_selling: true,
};

beforeEach(() => {
  state.links = [];
  state.published = [];
});

describe('ComboTagPreview empty states (R12)', () => {
  it('R12: a default that is not published says "No published price tag template"', () => {
    state.links = [link];
    state.published = [];
    render(<ComboTagPreview combo={combo as never} description="<p>x</p>" />);

    expect(screen.getByText('No published price tag template')).toBeInTheDocument();
    expect(screen.queryByText('No price tag template linked')).toBeNull();
  });

  it('R12: no link at all still says "No price tag template linked"', () => {
    render(<ComboTagPreview combo={combo as never} description="<p>x</p>" />);

    expect(screen.getByText('No price tag template linked')).toBeInTheDocument();
    expect(screen.queryByText('No published price tag template')).toBeNull();
  });
});

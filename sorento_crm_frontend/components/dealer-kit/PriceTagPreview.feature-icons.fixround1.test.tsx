/**
 * Feature icons review fix round 1 (B1): the portal live preview and the self-approval proof
 * forward the response's `feature_icons` into the payload the sheet draws with.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  __esModule: true,
  default: () => <div data-testid="viewer" />,
}));

import type { TagPreviewResponse } from '@/app/(auth)/portal/lib/price-tag-request-service';
import { previewPayload } from './PriceTagLivePreview';
import { buildSelfProof } from './PriceTagSelfApproval';

const template = {
  id: 'tpl',
  name: 'Basin A5',
  family: 'art_basin',
  doc: { layers: [], width_mm: 80, height_mm: 50 },
  print_size: { width_mm: 80, height_mm: 50 },
};
const ICONS = [{ id: 'hot', name: 'Hot', spec_key: 'water_supply', values: ['mixer'] }];

function response(key: string): TagPreviewResponse {
  return {
    lines: [{ line_id: key, tag_id: key, code: 'C', name: key, images: [] }],
    templates: { [key]: template },
    assets: { hot: 'https://cdn/hot.png' },
    images: {},
    fonts: [],
    feature_icons: ICONS,
  } as unknown as TagPreviewResponse;
}

describe('feature icons reach the portal payloads', () => {
  it('the live preview payload carries them', () => {
    const payload = previewPayload(
      [
        {
          key: 'k1',
          line_type: 'product',
          product_id: 'p1',
          product_set_id: null,
          tag_template_id: null,
        } as never,
      ],
      response('k1'),
    );
    expect(payload?.featureIcons).toEqual(ICONS);
  });

  it('the self-approval proof payload carries them', () => {
    const proof = buildSelfProof(
      [
        {
          id: 'l1',
          line_type: 'product',
          product_id: 'p1',
          product_set_id: null,
          quantity: 1,
          tags: [{ id: 't1', quantity: 1 }],
        } as never,
      ],
      { ...response('l1'), lines: [{ line_id: 'l1', tag_id: 't1', code: 'C', name: 'x', images: [] }] } as never,
    );
    expect(proof?.payload.featureIcons).toEqual(ICONS);
  });
});

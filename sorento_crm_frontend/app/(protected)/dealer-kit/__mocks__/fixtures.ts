/**
 * Phase 1 fixtures. These exist so the editor can be exercised - including its
 * empty, loading and error states - before any backend endpoint exists, per the
 * three-phase loop. Every shape here mirrors the documented API contract in
 * `../services/dealerKitService.ts`; when Phase 2 wires the real API, these are
 * deleted rather than left to rot beside it.
 */

import { createLayouts } from '@/lib/dealer-kit/deriveLayout';
import {
  DEFAULT_PRINT_PROFILE,
  type Asset,
  type Page,
  type PageSummary,
  type Section,
  type TileTemplate,
} from '@/lib/dealer-kit/types';

function section(
  id: string,
  name: string,
  blocks: Section['blocks'],
  placements: Record<string, { colStart: number; colSpan: number; rowStart: number; rowSpan: number }>,
  printMode: Section['printMode'] = 'include',
): Section {
  return {
    id,
    name,
    style: { background: 'transparent', paddingY: 'lg' },
    blocks,
    layouts: createLayouts(placements),
    printMode,
  };
}

export const MOCK_SECTIONS: Section[] = [
  section(
    'sec-cover',
    'Cover',
    [
      {
        id: 'blk-title',
        type: 'heading',
        props: { kind: 'heading', text: 'Sorento Bathroom Collection 2026', scale: '2xl', align: 'left' },
      },
      {
        id: 'blk-standfirst',
        type: 'text',
        props: {
          kind: 'text',
          text: 'Basins, mixers and shower systems for the 2026 season.',
          scale: 'lg',
          align: 'left',
        },
      },
    ],
    {
      'blk-title': { colStart: 1, colSpan: 8, rowStart: 1, rowSpan: 2 },
      'blk-standfirst': { colStart: 1, colSpan: 6, rowStart: 3, rowSpan: 1 },
    },
  ),
  section(
    'sec-feature',
    'Feature',
    [
      {
        id: 'blk-hero',
        type: 'image',
        props: { kind: 'image', assetId: 'asset-hero', alt: 'Bathroom scene', fit: 'cover' },
      },
      {
        id: 'blk-copy',
        type: 'text',
        props: {
          kind: 'text',
          text: 'Every basin in this range shares the same 40mm rim, so mixers interchange across the whole collection.',
          scale: 'base',
          align: 'left',
        },
      },
    ],
    {
      'blk-hero': { colStart: 1, colSpan: 7, rowStart: 1, rowSpan: 4 },
      'blk-copy': { colStart: 8, colSpan: 5, rowStart: 1, rowSpan: 2 },
    },
  ),
  section(
    'sec-basins',
    'Basins',
    [
      {
        id: 'blk-basins',
        type: 'collection',
        props: {
          kind: 'collection',
          collectionId: 'col-basins',
          tileTemplateId: 'tile-standard',
          columns: { desktop: 4, tablet: 2, mobile: 1 },
        },
      },
    ],
    { 'blk-basins': { colStart: 1, colSpan: 12, rowStart: 1, rowSpan: 4 } },
    'breakBefore',
  ),
];

export const MOCK_PAGE: Page = {
  id: 'page-2026-bathroom',
  name: 'Bathroom Catalogue 2026',
  slug: '2026-bathroom',
  updatedAt: '2026-07-24T09:12:00',
  publishedVersion: 2,
  latestVersion: 3,
  doc: { sections: MOCK_SECTIONS, printProfile: DEFAULT_PRINT_PROFILE },
  versions: [
    {
      id: 'ver-3',
      version: 3,
      commitMessage: 'Reflow basins after adding the 750mm',
      createdBy: 'Amirah Zulkifli',
      createdAt: '2026-07-24T09:12:00',
      labels: ['staging'],
    },
    {
      id: 'ver-2',
      version: 2,
      commitMessage: 'Season pricing applied',
      createdBy: 'Amirah Zulkifli',
      createdAt: '2026-07-21T16:40:00',
      labels: ['published'],
    },
    {
      id: 'ver-1',
      version: 1,
      commitMessage: 'Duplicated from 2025 edition',
      createdBy: 'Amirah Zulkifli',
      createdAt: '2026-07-18T11:05:00',
      labels: [],
    },
  ],
};

export const MOCK_PAGES: PageSummary[] = [
  {
    id: MOCK_PAGE.id,
    name: MOCK_PAGE.name,
    slug: MOCK_PAGE.slug,
    updatedAt: MOCK_PAGE.updatedAt,
    publishedVersion: 2,
    latestVersion: 3,
  },
  {
    id: 'page-kitchen-2026',
    name: 'Kitchen Sinks 2026',
    slug: '2026-kitchen',
    updatedAt: '2026-07-11T14:02:00',
    publishedVersion: 1,
    latestVersion: 1,
  },
  {
    id: 'page-trade-price-list',
    name: 'Trade Price List H2',
    slug: 'trade-price-h2',
    updatedAt: '2026-06-30T08:25:00',
    publishedVersion: null,
    latestVersion: 4,
  },
];

export const MOCK_ASSETS: Asset[] = [
  {
    id: 'asset-hero',
    name: 'Bathroom hero',
    kind: 'decorative',
    tags: ['bathroom', 'lifestyle'],
    url: 'https://picsum.photos/seed/sorento-bathroom-hero/1200/900',
    isVector: false,
  },
  {
    id: 'asset-logo',
    name: 'Sorento wordmark',
    kind: 'logo',
    tags: ['brand'],
    url: 'https://picsum.photos/seed/sorento-wordmark/400/120',
    isVector: true,
  },
  {
    id: 'asset-sirim',
    name: 'SIRIM certification',
    kind: 'badge',
    tags: ['certification', 'compliance'],
    url: 'https://picsum.photos/seed/sorento-sirim-badge/200/200',
    isVector: true,
  },
  {
    id: 'asset-watermark',
    name: 'Water efficiency label',
    kind: 'badge',
    tags: ['certification'],
    url: 'https://picsum.photos/seed/sorento-water-label/200/200',
    isVector: true,
  },
];

export const MOCK_TILE_TEMPLATES: TileTemplate[] = [
  {
    id: 'tile-standard',
    name: 'Standard product card',
    fields: ['image', 'name', 'code', 'price', 'badges'],
    updatedAt: '2026-07-20T10:00:00',
  },
  {
    id: 'tile-compact',
    name: 'Compact listing row',
    fields: ['name', 'code', 'price'],
    updatedAt: '2026-07-19T15:30:00',
  },
  {
    id: 'tile-spec',
    name: 'Spec-led card',
    fields: ['image', 'name', 'code', 'dimensions', 'badges'],
    updatedAt: '2026-07-02T09:45:00',
  },
];

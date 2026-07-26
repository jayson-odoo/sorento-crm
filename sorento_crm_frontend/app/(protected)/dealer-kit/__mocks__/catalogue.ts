/**
 * Phase 1 fixtures for collections, tiles and bundles.
 *
 * These stand in for endpoints that do not exist yet, so the picker, the tile
 * grid and the bundle card can be judged as UX before a resolver is written.
 * Phase 2 deletes everything here except what the component tests reuse.
 *
 * The shapes are the contract the backend will be held to - if a field is
 * awkward to render here, it is the wrong field, and now is the cheap moment to
 * find that out.
 */

import type {
  BundleSummary,
  CollectionSummary,
  ResolvedBundle,
  ResolvedTile,
  TileTemplate,
} from '@/lib/dealer-kit/types';

export interface PickerProduct {
  id: string;
  code: string;
  name: string;
  category: string;
  brand: string;
  price: string;
  isDiscontinued: boolean;
}

export const MOCK_PRODUCTS: PickerProduct[] = [
  {
    id: 'p-sink-3040',
    code: 'SK-3040',
    name: 'Undermount Kitchen Sink 760mm',
    category: 'Sinks',
    brand: 'Sorento',
    price: 'RM 1,290.00',
    isDiscontinued: false,
  },
  {
    id: 'p-sink-2210',
    code: 'SK-2210',
    name: 'Topmount Kitchen Sink 620mm',
    category: 'Sinks',
    brand: 'Sorento',
    price: 'RM 890.00',
    isDiscontinued: false,
  },
  {
    id: 'p-tap-1180',
    code: 'TP-1180',
    name: 'Pull-Out Kitchen Mixer',
    category: 'Taps',
    brand: 'Sorento',
    price: 'RM 640.00',
    isDiscontinued: false,
  },
  {
    id: 'p-tap-1102',
    code: 'TP-1102',
    name: 'Wall-Mounted Sink Tap',
    category: 'Taps',
    brand: 'Sorento',
    price: 'RM 320.00',
    isDiscontinued: true,
  },
  {
    id: 'p-shower-5501',
    code: 'SH-5501',
    name: 'Rain Shower Set 250mm',
    category: 'Showers',
    brand: 'Mocha',
    price: 'RM 1,750.00',
    isDiscontinued: false,
  },
  {
    id: 'p-shower-5310',
    code: 'SH-5310',
    name: 'Handheld Shower Kit',
    category: 'Showers',
    brand: 'Mocha',
    price: 'RM 410.00',
    isDiscontinued: false,
  },
];

export const MOCK_TILE_TEMPLATES: TileTemplate[] = [
  {
    id: 'tt-standard',
    name: 'Standard product tile',
    fields: ['image', 'name', 'code', 'price'],
    updatedAt: '2026-07-20T10:00:00',
  },
  {
    id: 'tt-detailed',
    name: 'Detailed tile with badges',
    fields: ['image', 'name', 'code', 'price', 'dimensions', 'badges'],
    updatedAt: '2026-07-22T10:00:00',
  },
  {
    id: 'tt-compact',
    name: 'Compact list tile',
    fields: ['name', 'code', 'price'],
    updatedAt: '2026-07-23T10:00:00',
  },
];

export const MOCK_COLLECTIONS: CollectionSummary[] = [
  {
    id: 'col-kitchen-2026',
    name: 'Kitchen range 2026',
    scope: 'library',
    memberCount: 3,
    updatedAt: '2026-07-24T09:00:00',
  },
  {
    id: 'col-showers',
    name: 'Shower sets',
    scope: 'library',
    memberCount: 2,
    updatedAt: '2026-07-18T09:00:00',
  },
];

export const MOCK_BUNDLES: BundleSummary[] = [
  { id: 'bn-kitchen-starter', name: 'Kitchen starter pack', price: 'RM 1,800.00', componentCount: 2, available: true },
  { id: 'bn-shower-combo', name: 'Shower combo', price: 'RM 2,000.00', componentCount: 2, available: false },
];

function tileFor(product: PickerProduct): ResolvedTile {
  return {
    productId: product.id,
    productCode: product.code,
    productName: product.name,
    // A staff viewer sees list price; the mock stands in for a resolved one.
    price: product.price,
    invoicePrice: null,
    imageUrl: null,
    dimensions: '760 x 440 x 220 mm',
    badges: product.category === 'Sinks' ? ['SIRIM'] : [],
  };
}

/** Stand-in for the server-side resolver: members minus anything discontinued (AC-G4). */
export function mockResolveCollection(productIds: string[]): ResolvedTile[] {
  return MOCK_PRODUCTS.filter(
    (product) => productIds.includes(product.id) && !product.isDiscontinued,
  ).map(tileFor);
}

export const MOCK_RESOLVED_BUNDLE: ResolvedBundle = {
  id: 'bn-kitchen-starter',
  name: 'Kitchen starter pack',
  price: 'RM 1,800.00',
  available: true,
  unavailableReason: null,
  components: [
    {
      productId: 'p-sink-3040',
      productCode: 'SK-3040',
      productName: 'Undermount Kitchen Sink 760mm',
      quantity: 1,
      allocated: 'RM 1,203.11',
      available: true,
    },
    {
      productId: 'p-tap-1180',
      productCode: 'TP-1180',
      productName: 'Pull-Out Kitchen Mixer',
      quantity: 1,
      allocated: 'RM 596.89',
      available: true,
    },
  ],
};

/** The case that must never render as orderable (AC-F10). */
export const MOCK_UNAVAILABLE_BUNDLE: ResolvedBundle = {
  id: 'bn-shower-combo',
  name: 'Shower combo',
  price: 'RM 2,000.00',
  available: false,
  unavailableReason: 'Wall-Mounted Sink Tap is discontinued',
  components: [
    {
      productId: 'p-shower-5501',
      productCode: 'SH-5501',
      productName: 'Rain Shower Set 250mm',
      quantity: 1,
      allocated: 'RM 1,634.15',
      available: true,
    },
    {
      productId: 'p-tap-1102',
      productCode: 'TP-1102',
      productName: 'Wall-Mounted Sink Tap',
      quantity: 1,
      allocated: 'RM 365.85',
      available: false,
    },
  ],
};

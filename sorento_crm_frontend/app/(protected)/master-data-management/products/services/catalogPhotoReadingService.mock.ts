/**
 * Phase 1 in-memory stand-in for the catalogue photo API (CATALOG-IMAGES). Seeded with the codes
 * from the approved mock. Sorting and paging are done here exactly as the server will do them.
 * S3 deletes this file and the `USE_MOCK` switch in the service.
 */

import type { DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  CatalogPhoto,
  CatalogPhotoAttachResult,
  CatalogPhotoConfidence,
  CatalogPhotoCounts,
  CatalogPhotoPatch,
  CatalogPhotoReading,
  CatalogPhotosParams,
  CatalogPhotoTab,
  ProductRef,
} from './catalogPhotoReadingService';

interface MockReading {
  id: string;
  file_name: string;
  created_at: string;
  startedAt: number;
  photos: CatalogPhoto[];
}

const DEMO_FILE = 'Sorento_Lite_DIY_CATALOG_UPDATE_22062026.pdf';
const readings = new Map<string, MockReading>();
let uploadSeq = 0;

function svg(label: string, tone: string): string {
  const body = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="${tone}"/><text x="80" y="64" font-size="11" text-anchor="middle" fill="#555" font-family="sans-serif">${label}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(body)}`;
}

function product(code: string): ProductRef {
  return { id: `mock-${code}`, product_code: code };
}

function photo(
  seq: number,
  page: number,
  code: string | null,
  extra: Partial<CatalogPhoto> = {},
): CatalogPhoto {
  const matched = code !== null && extra.product === undefined ? product(code) : null;
  return {
    id: `photo-${seq}`,
    page,
    position: seq,
    thumbnail_url: svg(code ?? `p${page}-photo-${seq}`, '#d5dae0'),
    image_url: svg(code ?? `p${page}-photo-${seq}`, '#d5dae0'),
    printed_code: code,
    block_codes: code ? [code] : [],
    placeholders: [],
    product: matched,
    rung: matched ? 'exact' : 'none',
    confidence: matched ? 'high' : 'none',
    suggestion: null,
    other_block_products: [],
    also_attach_product_ids: [],
    duplicate: null,
    decision: 'attach',
    attached_at: null,
    ...extra,
  };
}

function seed(): CatalogPhoto[] {
  let n = 0;
  const next = () => ++n;
  const rows: CatalogPhoto[] = [
    photo(next(), 2, 'SRTWT1906-BL-DIY', {
      duplicate: { attachment_id: 'a1', thumbnail_url: svg('On file now', '#c3cad3'), distance: 4 },
      decision: 'skip',
    }),
    photo(next(), 2, 'SRTWT1905-BL-DIY'),
    photo(next(), 2, 'SRTWT1906-DIY'),
    photo(next(), 14, 'SRTSS8807-GM-DIY'),
    photo(next(), 19, 'SRTBV120-DIY', {
      duplicate: { attachment_id: 'a2', thumbnail_url: svg('On file now', '#c3cad3'), distance: 7 },
      decision: 'skip',
    }),
    photo(next(), 7, 'SRTBF12613', {
      block_codes: ['SRTBF12613', 'SRTW2600'],
      placeholders: ['SRTWB_____'],
      other_block_products: [product('SRTW2600')],
    }),
    photo(next(), 1, null),
    photo(next(), 1, null),
    photo(next(), 15, null),
    photo(next(), 9, 'SRTW5112', {
      product: null,
      rung: 'none',
      confidence: 'none',
      suggestion: 'SRTW5112-MW',
    }),
  ];
  const mediums = new Set([4, 9, 15, 22, 31]);
  for (let i = 1; i <= 54; i += 1) {
    const code = `SRTGEN${String(100 + i)}-DIY`;
    const medium = mediums.has(i);
    const confidence: CatalogPhotoConfidence = medium ? 'medium' : 'high';
    rows.push(
      photo(next(), 3 + Math.floor(i / 3), code, {
        rung: medium ? 'suffix' : 'exact',
        confidence,
      }),
    );
  }
  return rows;
}

function tabOf(row: CatalogPhoto): CatalogPhotoTab {
  if (row.duplicate) return 'duplicate';
  if (row.decision === 'skip') return 'skipped';
  return row.product ? 'ready' : 'needs_product';
}

function willAttach(row: CatalogPhoto): boolean {
  return Boolean(row.product) && row.decision !== 'skip' && !row.attached_at;
}

function counts(photos: CatalogPhoto[]): CatalogPhotoCounts {
  const out: CatalogPhotoCounts = { ready: 0, duplicate: 0, needs_product: 0, skipped: 0, to_attach: 0 };
  for (const row of photos) {
    out[tabOf(row)] += 1;
    if (willAttach(row)) out.to_attach += 1;
  }
  return out;
}

function ensure(id: string): MockReading {
  let reading = readings.get(id);
  if (!reading) {
    reading = {
      id,
      file_name: DEMO_FILE,
      created_at: new Date().toISOString(),
      // The demo id is already read; an uploaded one walks queued, reading, ready.
      startedAt: id === 'demo' ? 0 : Date.now(),
      photos: seed(),
    };
    readings.set(id, reading);
  }
  return reading;
}

function view(reading: MockReading): CatalogPhotoReading {
  const age = Date.now() - reading.startedAt;
  const status = age < 3000 ? 'queued' : age < 8000 ? 'reading' : 'ready';
  const done = status === 'ready';
  return {
    id: reading.id,
    file_name: reading.file_name,
    status,
    page_count: done ? 32 : null,
    photo_count: done ? reading.photos.length : null,
    error: null,
    directory_id: 'mock-folder',
    created_at: reading.created_at,
    created_by_name: 'Test User',
    counts: done ? counts(reading.photos) : { ready: 0, duplicate: 0, needs_product: 0, skipped: 0, to_attach: 0 },
  };
}

const CONFIDENCE_RANK: Record<CatalogPhotoConfidence, number> = { high: 3, medium: 2, low: 1, none: 0 };

function sortKey(row: CatalogPhoto, key: string): string | number {
  switch (key) {
    case 'printed_code':
      return row.printed_code ?? '';
    case 'product_code':
      return row.product?.product_code ?? '';
    case 'confidence':
      return CONFIDENCE_RANK[row.confidence];
    default:
      return row.page * 1000 + row.position;
  }
}

const wait = <T,>(value: T): Promise<T> => new Promise((resolve) => setTimeout(() => resolve(value), 150));

export const catalogPhotoMock = {
  async upload(file: File): Promise<CatalogPhotoReading> {
    uploadSeq += 1;
    const reading = ensure(`upload-${uploadSeq}`);
    reading.file_name = file.name;
    return wait(view(reading));
  },

  async get(id: string): Promise<CatalogPhotoReading> {
    return wait(view(ensure(id)));
  },

  async list(id: string, params: CatalogPhotosParams): Promise<DataGridApiResponse<CatalogPhoto>> {
    const reading = ensure(id);
    const rows = reading.photos.filter((row) => tabOf(row) === params.tab);
    const key = params.sort ?? 'page';
    const dir = params.desc ? -1 : 1;
    rows.sort((a, b) => {
      const x = sortKey(a, key);
      const y = sortKey(b, key);
      const cmp = x < y ? -1 : x > y ? 1 : 0;
      return cmp * dir || a.page * 1000 + a.position - (b.page * 1000 + b.position);
    });
    const start = params.pageIndex * params.pageSize;
    return wait({
      data: rows.slice(start, start + params.pageSize),
      empty: rows.length === 0,
      pagination: { total: rows.length, page: params.pageIndex + 1 },
    });
  },

  async patch(
    id: string,
    photoId: string,
    patch: CatalogPhotoPatch,
    pickedProductCode?: string,
  ): Promise<CatalogPhoto> {
    const row = ensure(id).photos.find((item) => item.id === photoId);
    if (!row) throw new Error('Photo not found');
    if (row.attached_at) throw new Error('That photo is already attached');
    if (patch.product_id !== undefined) {
      row.product = patch.product_id
        ? { id: patch.product_id, product_code: pickedProductCode ?? row.suggestion ?? 'Product' }
        : null;
      row.rung = row.product ? 'alias' : 'none';
      row.confidence = row.product ? 'medium' : 'none';
      if (!row.product) row.also_attach_product_ids = [];
    }
    if (patch.decision !== undefined) {
      if ((patch.decision === 'keep_both' || patch.decision === 'replace') && !row.duplicate) {
        throw new Error('Only a photo that looks like an existing one can do that');
      }
      row.decision = patch.decision;
    }
    if (patch.also_attach_product_ids) row.also_attach_product_ids = patch.also_attach_product_ids;
    return wait({ ...row });
  },

  async attach(id: string): Promise<CatalogPhotoAttachResult> {
    const reading = ensure(id);
    const now = new Date().toISOString();
    const productIds = new Set<string>();
    let attached = 0;
    let replaced = 0;
    for (const row of reading.photos) {
      if (!willAttach(row) || !row.product) continue;
      row.attached_at = now;
      attached += 1;
      productIds.add(row.product.id);
      if (row.decision === 'replace') replaced += 1;
      for (const extra of row.also_attach_product_ids) {
        attached += 1;
        productIds.add(extra);
      }
    }
    const skipped = reading.photos.filter((row) => row.decision === 'skip').length;
    return wait({ attached, replaced, skipped, products: productIds.size });
  },
};

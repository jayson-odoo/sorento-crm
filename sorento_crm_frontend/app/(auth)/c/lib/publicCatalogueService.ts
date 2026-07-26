/**
 * Public catalogue reader.
 *
 * Deliberately NOT `apiFetch`: that resolves a NextAuth token before every
 * call, and a consumer opening a shared link has no session to resolve. A plain
 * relative fetch also keeps this page working for someone who is not, and never
 * will be, a user of the CRM.
 *
 * ---------------------------------------------------------------------------
 * CONTRACT
 *
 * GET /api/v1/public/c/{companyCode}/{slug}  -> { name, slug, doc }
 *
 * 404 covers all three of "no such company", "no such page" and "not
 * published" - on purpose. An anonymous reader does not get to tell them apart.
 * ---------------------------------------------------------------------------
 */

import type { PageDoc } from '@/lib/dealer-kit/types';

export interface PublishedCatalogue {
  name: string;
  slug: string;
  doc: PageDoc;
}

export class CatalogueNotFoundError extends Error {
  constructor() {
    super('Catalogue not found');
    this.name = 'CatalogueNotFoundError';
  }
}

function apiBase(): string {
  const env = process.env.NEXT_PUBLIC_API_URL;
  return env ? env.replace(/\/$/, '') : '';
}

export async function readPublishedCatalogue(
  companyCode: string,
  slug: string,
): Promise<PublishedCatalogue> {
  const path = `/api/v1/public/c/${encodeURIComponent(companyCode)}/${encodeURIComponent(slug)}`;
  const response = await fetch(`${apiBase()}${path}`, { cache: 'no-store' });

  if (response.status === 404) throw new CatalogueNotFoundError();
  if (!response.ok) throw new Error('This catalogue could not be loaded right now.');

  return (await response.json()) as PublishedCatalogue;
}

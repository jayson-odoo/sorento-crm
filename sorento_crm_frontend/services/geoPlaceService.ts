import { extractApiError } from '@/lib/api-client';

/**
 * Coordinates to a place name, for a signature pad that is still capturing.
 *
 * Contract, matching `app/api/v1/public/geo.py` exactly:
 *
 *   GET /api/v1/public/geo/nearest-place?lat=&lng=  -> NearestPlace
 *
 * The lookup stays on the SERVER on purpose. `geo_places` is the one definition the PDF renders
 * from, and a copy of that table in JavaScript is how the screen and the printed document start
 * disagreeing about where somebody stood. So the browser supplies the numbers and asks.
 *
 * Plain `fetch`, not `apiFetch`, and public on purpose: the customer counter-signing has no
 * session and never will, and a staff member opening the same link should not be sending their
 * own bearer token to a public endpoint. Same path the counter-sign page and the contact portal
 * already take (`app/(auth)/quotation-sign/services/quotationSignService.ts`).
 */

const PATH = '/api/v1/public/geo/nearest-place';

/**
 * Where the backend actually is.
 *
 * A relative path alone is NOT enough: the dev rewrite in `next.config` only proxies
 * `/api/v1/*` when `NEXT_PUBLIC_API_URL` is unset. Every deployed environment sets it, and the
 * relative URL would then resolve against the Next origin, which serves no such route.
 */
function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  return configured ? configured.replace(/\/$/, '') : '';
}

export type NearestPlace = {
  lat: number;
  lng: number;
  /** `3.03927, 101.80660`. Always present: the numbers are the evidence. */
  coordinates: string;
  /**
   * What to show: `near Kajang, Selangor (3.03927, 101.80660)`, or the bare coordinates when
   * nothing known is close enough to name honestly.
   */
  description: string;
  place: string | null;
  place_name: string | null;
  state: string | null;
  distance_km: number | null;
};

export async function getNearestPlace(
  lat: number,
  lng: number,
  signal?: AbortSignal,
): Promise<NearestPlace> {
  const query = new URLSearchParams({ lat: String(lat), lng: String(lng) });
  const response = await fetch(`${apiBase()}${PATH}?${query.toString()}`, { signal });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not name this location'));
  }
  return response.json();
}

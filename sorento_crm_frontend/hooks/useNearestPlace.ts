'use client';

import * as React from 'react';
import { getNearestPlace } from '@/services/geoPlaceService';

/**
 * The place name for a fix the browser has just granted, while the pad is still capturing.
 *
 * Three rules, and each one is there because breaking it would be worse than showing nothing:
 *
 * - **Never asked without a fix.** No coordinates, no question.
 * - **Never blocking.** A slow or failed lookup leaves the coordinates on screen and signing
 *   carries on. The place is a convenience; the numbers are the record.
 * - **Never held against different coordinates.** The answer is dropped the instant the fix
 *   moves, so a name from one position can never be printed beside another one's numbers.
 *
 * Deliberately not react-query: this is a one-shot lookup on a component that also runs on the
 * PUBLIC counter-sign page, which has no QueryClientProvider above it.
 */
export function useNearestPlace(
  coords: { lat: number; lng: number } | null,
): string | null {
  const [place, setPlace] = React.useState<{ lat: number; lng: number; name: string } | null>(
    null,
  );

  React.useEffect(() => {
    if (!coords) {
      setPlace(null);
      return;
    }
    const controller = new AbortController();
    let alive = true;
    const { lat, lng } = coords;
    getNearestPlace(lat, lng, controller.signal)
      .then((answer) => {
        // `place` is the bare label ("Kajang, Selangor"), not `description` (which still carries
        // the coordinates for the server-rendered PDF). The pad shows only the readable name;
        // the exact figures live on the stored signature row, not on this label.
        if (alive && answer.place) setPlace({ lat, lng, name: answer.place });
      })
      .catch(() => {
        // A failed lookup is not an error worth showing: the coordinates already on screen are
        // the answer, and interrupting somebody mid-signature over a place name would be absurd.
      });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [coords]);

  // Pinned to the coordinates it was resolved for. A stale name beside a new fix would be a
  // confident lie on a record somebody is about to put their name to.
  if (!coords || !place) return null;
  return place.lat === coords.lat && place.lng === coords.lng ? place.name : null;
}

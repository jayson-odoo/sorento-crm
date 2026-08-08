'use client';

/**
 * Where the technician is going: structured fields, and a map you can actually move the pin on.
 *
 * The first version was one textarea and a "Move pin" button that only re-read the browser's
 * geolocation. A consumer typed "kajang" and it was accepted as an address - which is a van
 * dispatched to a town - and there was no way to correct a pin that landed on the wrong side
 * of it, because there was no map to correct it on.
 *
 * **The pin populates the fields, not the other way round.** Dragging the marker reverse-
 * geocodes and fills line 1, postcode, city and state, because a consumer standing in the
 * house knows where they are and does not enjoy typing a postcode. Every field stays
 * editable afterwards: the geocoder is frequently close-but-wrong on Malaysian addresses,
 * and a locked field would make its error unfixable.
 *
 * **The pin never blocks** (AC-M38). No key configured, permission denied, no GPS, offline -
 * all of them fall through to the typed fields and a submittable form. A consumer who cannot
 * close the form at 6pm in a basement phones the office instead, which is worse data than
 * not asking.
 *
 * **The address and the pin are both kept and never reconciled** (AC-M39). The pin is what
 * gets navigated to, the address is what goes on documents. Asking a consumer to resolve a
 * disagreement they cannot perceive helps nobody.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, MapPin } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';

export interface SiteAddress {
  line1: string;
  line2: string;
  postcode: string;
  city: string;
  state: string;
  country: string;
}

export const EMPTY_SITE_ADDRESS: SiteAddress = {
  line1: '',
  line2: '',
  postcode: '',
  city: '',
  state: '',
  country: 'Malaysia',
};

/** The 13 states and 3 federal territories. A free-text state produces "Selangor",
 *  "selangor" and "SGR" in the same column and no report can group them. */
export const MALAYSIAN_STATES = [
  'Johor',
  'Kedah',
  'Kelantan',
  'Melaka',
  'Negeri Sembilan',
  'Pahang',
  'Perak',
  'Perlis',
  'Pulau Pinang',
  'Sabah',
  'Sarawak',
  'Selangor',
  'Terengganu',
  'W.P. Kuala Lumpur',
  'W.P. Labuan',
  'W.P. Putrajaya',
];

export type Coords = { latitude: number; longitude: number };

/** One line from the parts, matching what the server composes. Used for the preview only. */
export function composeSiteAddress(address: SiteAddress): string {
  const postcodeCity = [address.postcode, address.city]
    .map((part) => part.trim())
    .filter(Boolean)
    .join(' ');
  return [address.line1, address.line2, postcodeCity, address.state, address.country]
    .map((part) => (part || '').trim())
    .filter(Boolean)
    .join(', ');
}

/**
 * Pull the Malaysian pieces out of a Google reverse-geocode result.
 *
 * Exported for its own test: the component types are unmockable in jsdom, and this mapping
 * is the part that can be wrong while everything renders perfectly.
 */
export function addressFromGeocode(
  components: Array<{ long_name: string; short_name: string; types: string[] }>,
  formatted: string,
): Partial<SiteAddress> {
  const pick = (type: string) => components.find((c) => c.types.includes(type))?.long_name ?? '';

  const streetNumber = pick('street_number');
  const route = pick('route');
  const premise = pick('premise');
  // `sublocality` is the taman/section, which on a Malaysian address is the line that makes
  // it findable - Google files it below the city and it is not optional here.
  const sublocality =
    pick('sublocality_level_1') || pick('sublocality') || pick('neighborhood');

  const line1 = [premise, streetNumber, route].filter(Boolean).join(' ').trim();

  return {
    // Falls back to the formatted string's first segment rather than to nothing: a blank
    // line 1 under a dropped pin looks like the map failed.
    line1: line1 || formatted.split(',')[0]?.trim() || '',
    line2: sublocality,
    postcode: pick('postal_code'),
    city: pick('locality') || pick('administrative_area_level_2'),
    state: pick('administrative_area_level_1'),
    country: pick('country') || 'Malaysia',
  };
}

// Google's own typings are not installed; this is the surface actually used.
type GoogleMaps = any; // eslint-disable-line @typescript-eslint/no-explicit-any

declare global {
  interface Window {
    google?: { maps?: GoogleMaps };
    __sorentoMapsLoader__?: Promise<void>;
  }
}

/** Load the Maps script once per page, however many components ask for it. */
function loadGoogleMaps(apiKey: string): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve();
  if (window.google?.maps) return Promise.resolve();
  if (window.__sorentoMapsLoader__) return window.__sorentoMapsLoader__;

  window.__sorentoMapsLoader__ = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    // `loading=async` is Google's supported bootstrap. Without it the API logs a performance
    // warning on every load, which is noise in the console we check for real regressions.
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&libraries=places&loading=async`;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => {
      // Clear the cached promise so a later attempt can retry - a restricted key that gets
      // fixed in Google Cloud should not need a page reload to start working.
      window.__sorentoMapsLoader__ = undefined;
      reject(new Error('maps_script_failed'));
    };
    document.head.appendChild(script);
  });
  return window.__sorentoMapsLoader__;
}

// Kuala Lumpur. Only used when there is no pin and no geolocation, so the map opens
// somewhere recognisable rather than in the Atlantic.
const FALLBACK_CENTRE = { lat: 3.139, lng: 101.6869 };

export interface SitePickerProps {
  address: SiteAddress;
  onAddress: (next: SiteAddress) => void;
  coords: Coords | null;
  onCoords: (next: Coords | null) => void;
  /** Null when the tenant has configured no key: fields only, no map, still submittable. */
  apiKey: string | null;
}

export function SitePicker({ address, onAddress, coords, onCoords, apiKey }: SitePickerProps) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapObj = useRef<GoogleMaps>(null);
  const markerObj = useRef<GoogleMaps>(null);
  const [mapState, setMapState] = useState<'idle' | 'loading' | 'ready' | 'failed'>('idle');
  const [locating, setLocating] = useState(false);

  const set = (patch: Partial<SiteAddress>) => onAddress({ ...address, ...patch });

  /** Reverse-geocode and fill the fields. Best-effort: a failure leaves the pin and the
   *  typed fields exactly as they were. */
  const fillFromCoords = useCallback(
    (next: Coords) => {
      const maps = window.google?.maps;
      if (!maps) return;
      const geocoder = new maps.Geocoder();
      geocoder.geocode(
        { location: { lat: next.latitude, lng: next.longitude } },
        (results: any[], status: string) => { // eslint-disable-line @typescript-eslint/no-explicit-any
          if (status !== 'OK' || !results?.length) return;
          const parsed = addressFromGeocode(
            results[0].address_components ?? [],
            results[0].formatted_address ?? '',
          );
          // Never blank a field the consumer already filled: the geocoder is often
          // close-but-wrong here, and overwriting a corrected postcode with its guess is
          // the one thing that would make people stop touching the map.
          onAddress({
            line1: address.line1 || parsed.line1 || '',
            line2: address.line2 || parsed.line2 || '',
            postcode: address.postcode || parsed.postcode || '',
            city: address.city || parsed.city || '',
            state: address.state || parsed.state || '',
            country: address.country || parsed.country || 'Malaysia',
          });
        },
      );
    },
    [address, onAddress],
  );

  const placePin = useCallback(
    (next: Coords) => {
      onCoords(next);
      const maps = window.google?.maps;
      if (maps && mapObj.current) {
        const position = { lat: next.latitude, lng: next.longitude };
        mapObj.current.setCenter(position);
        if (markerObj.current) markerObj.current.setPosition(position);
      }
      fillFromCoords(next);
    },
    [fillFromCoords, onCoords],
  );

  // Build the map once the script is in.
  //
  // Guarded by a REF, not by `mapState`. Keying the effect on state it also sets was a
  // race that hung the map on a spinner forever: setting 'loading' changed a dependency,
  // React ran the cleanup for the in-flight attempt (`cancelled = true`), re-ran the
  // effect, and the re-run bailed out because the state was no longer 'idle'. When the
  // script finally arrived the only attempt that could have built the map had already
  // been told to stand down. Nothing errored; it just never finished.
  const startedRef = useRef(false);
  useEffect(() => {
    if (!apiKey || startedRef.current) return;
    startedRef.current = true;
    setMapState('loading');
    let cancelled = false;
    loadGoogleMaps(apiKey)
      .then(() => {
        if (cancelled || !mapRef.current) return;
        const maps = window.google?.maps;
        // `window.google.maps` is truthy the moment the bootstrap runs, but the modern
        // loader fetches the constructors separately - so `maps.Map` can still be
        // undefined here, and calling it would throw inside a promise chain.
        if (!maps || typeof maps.Map !== 'function') {
          setMapState('failed');
          return;
        }
        const centre = coords
          ? { lat: coords.latitude, lng: coords.longitude }
          : FALLBACK_CENTRE;
        mapObj.current = new maps.Map(mapRef.current, {
          center: centre,
          zoom: coords ? 17 : 11,
          disableDefaultUI: true,
          zoomControl: true,
        });
        markerObj.current = new maps.Marker({
          position: centre,
          map: mapObj.current,
          draggable: true,
        });
        markerObj.current.addListener('dragend', () => {
          const pos = markerObj.current.getPosition();
          placePin({ latitude: pos.lat(), longitude: pos.lng() });
        });
        // Tapping the map moves the pin too. On a phone, dragging a marker with a thumb is
        // fiddly and tapping where you live is not.
        mapObj.current.addListener('click', (event: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
          placePin({ latitude: event.latLng.lat(), longitude: event.latLng.lng() });
        });
        setMapState('ready');
      })
      .catch(() => {
        if (!cancelled) setMapState('failed');
      });
    return () => {
      cancelled = true;
    };
    // Built once. Re-running on every coords change would rebuild the map under the pin.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey]);

  const useMyLocation = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        placePin({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
      },
      () => {
        // Denied or unavailable. Silent on purpose: the consumer said no, and nagging them
        // about it on the last screen of a complaint is not the moment.
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="text-sm font-medium">Address line 1</span>
          <Input
            value={address.line1}
            onChange={(e) => set({ line1: e.target.value })}
            placeholder="Unit / house number and street"
          />
        </label>
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="text-sm font-medium">Address line 2</span>
          <Input
            value={address.line2}
            onChange={(e) => set({ line2: e.target.value })}
            placeholder="Taman, section, building (optional)"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Postcode</span>
          <Input
            value={address.postcode}
            inputMode="numeric"
            maxLength={5}
            onChange={(e) => set({ postcode: e.target.value.replace(/\D/g, '') })}
            placeholder="43000"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">City</span>
          <Input
            value={address.city}
            onChange={(e) => set({ city: e.target.value })}
            placeholder="Kajang"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">State</span>
          {/* A closed list: free text produces "Selangor", "selangor" and "SGR" in one
              column and no report can group them. */}
          <SearchableSelect
            value={address.state}
            onChange={(value) => set({ state: value })}
            options={MALAYSIAN_STATES.map((name) => ({ value: name, label: name }))}
            placeholder="Select a state"
            clearable
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Country</span>
          <Input
            value={address.country}
            onChange={(e) => set({ country: e.target.value })}
            placeholder="Malaysia"
          />
        </label>
      </div>

      <div className="rounded-lg border p-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-medium">Drop a pin (optional)</p>
            <p className="text-xs text-muted-foreground">
              {coords
                ? 'Pin saved - this is what the technician will navigate to. Drag it or tap the map to move it.'
                : mapState === 'failed'
                  ? 'The map could not load. The address above is enough.'
                  : apiKey
                    ? 'Tap the map or drag the pin. We will fill in the address for you.'
                    : 'Helps our technician find you. You can skip this.'}
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="h-8 shrink-0"
            onClick={useMyLocation}
            disabled={locating}
          >
            {locating ? (
              <Loader2 className="mr-1.5 size-3 animate-spin" />
            ) : (
              <MapPin className="mr-1.5 size-3" />
            )}
            Use my location
          </Button>
        </div>

        {apiKey && mapState !== 'failed' ? (
          <div className="relative mt-3">
            <div ref={mapRef} className="h-64 w-full rounded-md bg-muted" />
            {mapState !== 'ready' ? (
              <div
                data-testid="site-map-spinner"
                className="absolute inset-0 flex items-center justify-center rounded-md bg-muted/60"
              >
                <Loader2 className="size-5 animate-spin text-muted-foreground" />
              </div>
            ) : null}
          </div>
        ) : null}


      </div>
    </div>
  );
}

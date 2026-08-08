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
import { Loader2, MapPin, Search } from 'lucide-react';

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

/** One prediction from Google's autocomplete, reduced to what the list renders. */
export interface PlaceSuggestion {
  placeId: string;
  primary: string;
  secondary: string;
}

/** True when the consumer has typed nothing into the address at all.
 *
 * Decides whether a dropped pin fills the fields outright or has to ask first. With an
 * empty form there is nothing to lose and asking is friction; with anything typed, the
 * typed value is a person's own answer and silently replacing it is the behaviour that
 * makes people stop touching the map.
 */
export function isAddressBlank(address: SiteAddress): boolean {
  return !['line1', 'line2', 'postcode', 'city', 'state']
    .map((key) => (address[key as keyof SiteAddress] || '').trim())
    .some(Boolean);
}

/** What changes if a proposed address were applied, as field labels.
 *
 * Shown so the question is answerable. "Use this address?" beside a one-line summary asks
 * somebody to diff two addresses in their head; naming the fields that would change makes
 * it a decision instead of a guess.
 */
export function changedFields(current: SiteAddress, next: Partial<SiteAddress>): string[] {
  const LABELS: Array<[keyof SiteAddress, string]> = [
    ['line1', 'Address line 1'],
    ['line2', 'Address line 2'],
    ['postcode', 'Postcode'],
    ['city', 'City'],
    ['state', 'State'],
  ];
  return LABELS.filter(([key]) => {
    const proposed = (next[key] || '').trim();
    if (!proposed) return false;
    return proposed !== (current[key] || '').trim();
  }).map(([, label]) => label);
}

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

/**
 * Load the Maps script once per page, however many components ask for it.
 *
 * **`loading=async` requires `callback=`.** That pairing is the whole of this function.
 * `loading=async` is Google's supported bootstrap and the only form that does not log a
 * performance warning, but it changes what `onload` means: the script fires `onload`
 * before the constructors exist, and `google.maps.Map` is still `undefined` at that
 * moment. Measured on a working key - `Map`, `Geocoder` and `places` are all undefined at
 * `onload` and all present once the named callback runs. Resolving on `onload` therefore
 * made a perfectly good key report "The map could not load" every time.
 *
 * The callback name is fixed rather than unique per call: the promise below is already a
 * per-page singleton, so a second name would only exist to be leaked.
 */
function loadGoogleMaps(apiKey: string): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve();
  // Constructors present means a previous load already finished - including one from
  // another component on the page.
  if (typeof window.google?.maps?.Map === 'function') return Promise.resolve();
  if (window.__sorentoMapsLoader__) return window.__sorentoMapsLoader__;

  window.__sorentoMapsLoader__ = new Promise<void>((resolve, reject) => {
    const CALLBACK = '__sorentoMapsReady__';
    (window as unknown as Record<string, unknown>)[CALLBACK] = () => resolve();
    const script = document.createElement('script');
    script.src =
      `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}` +
      `&libraries=places&loading=async&callback=${CALLBACK}`;
    script.async = true;
    script.onerror = () => reject(new Error('maps_script_failed'));
    document.head.appendChild(script);
  }).catch((error) => {
    // Clear the cached promise so a later attempt can retry - a restricted key that gets
    // fixed in Google Cloud should not need a page reload to start working.
    window.__sorentoMapsLoader__ = undefined;
    throw error;
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

  // What the last pin move resolved to, held as a PROPOSAL rather than applied.
  //
  // The previous version filled only fields that were still empty, so the first drop
  // populated the form and every drop after it did nothing at all - no fill, no message,
  // no way to tell whether the map had even understood the new position. Moving a pin and
  // seeing nothing happen reads as broken.
  //
  // Now the resolved address is always shown, and applying it is the consumer's call
  // (AC-M39: the pin and the address are both kept and never auto-reconciled). The one
  // exception is a blank form, where there is nothing to overwrite and asking is pure
  // friction.
  const [proposal, setProposal] = useState<{
    formatted: string;
    parsed: Partial<SiteAddress>;
    applied: boolean;
  } | null>(null);

  // The address search. Its own state because the box is a search, not a form field:
  // what is typed here is a query, and the answer is one of the suggestions.
  const [searchText, setSearchText] = useState('');
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [searching, setSearching] = useState(false);
  const sessionToken = useRef<GoogleMaps>(null);

  // The address, reachable from callbacks that outlive the render they were created in.
  //
  // The map's `click` and `dragend` listeners are registered ONCE, when the map is built,
  // and they hold whatever closure existed at that moment - which is the first render,
  // where the address is still empty. Reading `address` directly from those callbacks
  // meant every pin move after the first still believed the form was blank, so it
  // auto-applied over answers the consumer had already given instead of asking. Caught in
  // a live walk: searching for an address filled the fields, and the very next pin drop
  // silently overwrote them.
  const addressRef = useRef(address);
  useEffect(() => {
    addressRef.current = address;
  }, [address]);

  const applyParsed = useCallback(
    (parsed: Partial<SiteAddress>) => {
      const current = addressRef.current;
      onAddress({
        line1: parsed.line1 ?? current.line1,
        line2: parsed.line2 ?? current.line2,
        postcode: parsed.postcode ?? current.postcode,
        city: parsed.city ?? current.city,
        state: parsed.state ?? current.state,
        country: parsed.country || current.country || 'Malaysia',
      });
    },
    [onAddress],
  );

  /** Reverse-geocode a pin and offer what it found. Best-effort: a failure leaves the pin
   *  and the typed fields exactly as they were. */
  const describeCoords = useCallback(
    (next: Coords) => {
      const maps = window.google?.maps;
      if (!maps) return;
      const geocoder = new maps.Geocoder();
      geocoder.geocode(
        { location: { lat: next.latitude, lng: next.longitude } },
        (results: any[], status: string) => { // eslint-disable-line @typescript-eslint/no-explicit-any
          if (status !== 'OK' || !results?.length) {
            setProposal(null);
            return;
          }
          const formatted = results[0].formatted_address ?? '';
          const parsed = addressFromGeocode(results[0].address_components ?? [], formatted);
          // Read through the ref, not the closure: this runs from a listener registered
          // once at map build time (see `addressRef`).
          const autoApply = isAddressBlank(addressRef.current);
          if (autoApply) applyParsed(parsed);
          setProposal({ formatted, parsed, applied: autoApply });
        },
      );
    },
    [applyParsed],
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
      describeCoords(next);
    },
    [describeCoords, onCoords],
  );

  /**
   * Address predictions as the consumer types.
   *
   * Uses the LEGACY `AutocompleteService`, deliberately. The modern
   * `AutocompleteSuggestion` runs on Places API (New), which is a separate product that
   * has to be enabled and billed on its own; on a key with only Maps JS, Geocoding and
   * the classic Places API enabled it fails with "API key not valid", which reads as a
   * broken key rather than a missing subscription. The legacy service works on the
   * enablement this tenant already has.
   */
  const fetchSuggestions = useCallback((input: string) => {
    const maps = window.google?.maps;
    const query = input.trim();
    if (!maps?.places?.AutocompleteService || query.length < 3) {
      setSuggestions([]);
      return;
    }
    if (!sessionToken.current && maps.places.AutocompleteSessionToken) {
      // One token per search-then-pick. Google bills the whole sequence as a single
      // session; without it every keystroke is charged as its own request.
      sessionToken.current = new maps.places.AutocompleteSessionToken();
    }
    setSearching(true);
    new maps.places.AutocompleteService().getPlacePredictions(
      {
        input: query,
        // Malaysia only. A Malaysian consumer searching "jalan sl 1" should not have to
        // scroll past a street in Jakarta.
        componentRestrictions: { country: 'my' },
        sessionToken: sessionToken.current ?? undefined,
      },
      (predictions: any[] | null) => { // eslint-disable-line @typescript-eslint/no-explicit-any
        setSearching(false);
        setSuggestions(
          (predictions ?? []).slice(0, 5).map((p) => ({
            placeId: p.place_id,
            primary: p.structured_formatting?.main_text ?? p.description ?? '',
            secondary: p.structured_formatting?.secondary_text ?? '',
          })),
        );
      },
    );
  }, []);

  // Debounced, because this is billed per request and a Malaysian address is long enough
  // that firing on every keystroke would multiply the cost of one search by twenty.
  useEffect(() => {
    const handle = setTimeout(() => fetchSuggestions(searchText), 350);
    return () => clearTimeout(handle);
  }, [searchText, fetchSuggestions]);

  /**
   * Take a chosen suggestion: move the pin there AND fill the fields.
   *
   * Applied outright, unlike a dragged pin. Picking a specific address off a list is an
   * unambiguous statement of intent - there is nothing to ask about - whereas nudging a
   * marker is as likely to be someone fine-tuning where the van should stop.
   */
  const chooseSuggestion = useCallback(
    (suggestion: PlaceSuggestion) => {
      const maps = window.google?.maps;
      if (!maps) return;
      setSuggestions([]);
      setSearchText('');
      // Resolved through the Geocoder by place id rather than through PlacesService: it
      // returns `address_components` in the exact shape `addressFromGeocode` already
      // parses, and it needs no map div to construct.
      new maps.Geocoder().geocode(
        { placeId: suggestion.placeId },
        (results: any[], status: string) => { // eslint-disable-line @typescript-eslint/no-explicit-any
          // The session ends with the pick, whatever the outcome.
          sessionToken.current = null;
          if (status !== 'OK' || !results?.length) return;
          const formatted = results[0].formatted_address ?? '';
          const parsed = addressFromGeocode(results[0].address_components ?? [], formatted);
          applyParsed(parsed);
          setProposal({ formatted, parsed, applied: true });
          const location = results[0].geometry?.location;
          if (location) {
            const next = { latitude: location.lat(), longitude: location.lng() };
            onCoords(next);
            if (mapObj.current) {
              const position = { lat: next.latitude, lng: next.longitude };
              mapObj.current.setCenter(position);
              mapObj.current.setZoom(17);
              if (markerObj.current) markerObj.current.setPosition(position);
            }
          }
        },
      );
    },
    [applyParsed, onCoords],
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

  const pendingFields = proposal && !proposal.applied ? changedFields(address, proposal.parsed) : [];

  return (
    <div className="flex flex-col gap-4">
      {/* Search first, because it is the fastest way to a correct address and the one
          people already know how to use. Typing the fields by hand still works, and so
          does the pin; this is the shortcut, not a gate. */}
      {apiKey && mapState !== 'failed' ? (
        <div className="relative">
          <span className="text-sm font-medium">Search for your address</span>
          <div className="relative mt-1.5">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Start typing, e.g. Jalan SL 1 Bandar Sungai Long"
              className="pl-9"
              autoComplete="off"
            />
            {searching ? (
              <Loader2 className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
            ) : null}
          </div>
          {suggestions.length > 0 ? (
            <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border bg-popover shadow-md">
              {suggestions.map((suggestion) => (
                <li key={suggestion.placeId}>
                  <button
                    type="button"
                    className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left hover:bg-accent"
                    onClick={() => chooseSuggestion(suggestion)}
                  >
                    <span className="text-sm font-medium">{suggestion.primary}</span>
                    {suggestion.secondary ? (
                      <span className="text-xs text-muted-foreground">
                        {suggestion.secondary}
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

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

        {/* What the pin resolved to. Always shown once there is one, whether or not it
            was applied - a marker that moves and says nothing is a marker that looks
            broken, which is what this screen did before. */}
        {proposal ? (
          <div className="mt-3 rounded-md border bg-muted/40 p-3">
            <p className="text-xs text-muted-foreground">This pin is at</p>
            <p className="mt-0.5 text-sm font-medium break-words">{proposal.formatted}</p>
            {proposal.applied ? (
              <p className="mt-1 text-xs text-muted-foreground">
                We filled in the address above. Change anything that is not right.
              </p>
            ) : pendingFields.length > 0 ? (
              <>
                <p className="mt-1 text-xs text-muted-foreground">
                  Use it? This would change {pendingFields.join(', ')}.
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    className="h-8"
                    onClick={() => {
                      applyParsed(proposal.parsed);
                      setProposal({ ...proposal, applied: true });
                    }}
                  >
                    Use this address
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-8"
                    onClick={() => setProposal(null)}
                  >
                    Keep what I typed
                  </Button>
                </div>
              </>
            ) : (
              <p className="mt-1 text-xs text-muted-foreground">
                This matches the address above.
              </p>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

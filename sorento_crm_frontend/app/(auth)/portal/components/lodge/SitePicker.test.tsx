/**
 * The address a van is dispatched to.
 *
 * The step this replaces was one textarea. A consumer typed `kajang` and the form accepted
 * it, which is a technician sent to a town of 200,000 people. Postcode and state are also
 * what every printed document needs, and neither can be recovered afterwards from a sentence
 * somebody typed in a hurry.
 *
 * Two pieces are worth their own tests. `addressFromGeocode` is where a pin dropped on the
 * right house can still produce the wrong fields - Google files the taman as a
 * `sublocality`, below the city, and on a Malaysian address that is the line that makes it
 * findable. `composeSiteAddress` has to match what the server composes, or the one-liner
 * stored on the complaint disagrees with the parts stored beside it.
 *
 * The map itself is not tested here: it is Google's canvas, unmockable in jsdom, and
 * asserting that a script tag was appended would test the loader rather than the outcome.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';

import {
  EMPTY_SITE_ADDRESS,
  MALAYSIAN_STATES,
  SitePicker,
  addressFromGeocode,
  changedFields,
  composeSiteAddress,
  isAddressBlank,
} from './SitePicker';

function component(long_name: string, types: string[]) {
  return { long_name, short_name: long_name, types };
}

describe('addressFromGeocode', () => {
  it('builds line 1 from the street number and route', () => {
    const parsed = addressFromGeocode(
      [
        component('5', ['street_number']),
        component('Jalan Impiana 1A', ['route']),
        component('Taman Bukit Impiana', ['sublocality_level_1']),
        component('Kajang', ['locality']),
        component('Selangor', ['administrative_area_level_1']),
        component('43000', ['postal_code']),
        component('Malaysia', ['country']),
      ],
      '5, Jalan Impiana 1A, Taman Bukit Impiana, 43000 Kajang, Selangor, Malaysia',
    );
    expect(parsed.line1).toBe('5 Jalan Impiana 1A');
    expect(parsed.postcode).toBe('43000');
    expect(parsed.city).toBe('Kajang');
    expect(parsed.state).toBe('Selangor');
  });

  it('keeps the taman as line 2, because that is what makes an address findable here', () => {
    const parsed = addressFromGeocode(
      [
        component('Taman Bukit Impiana', ['sublocality_level_1']),
        component('Kajang', ['locality']),
      ],
      'Taman Bukit Impiana, Kajang',
    );
    expect(parsed.line2).toBe('Taman Bukit Impiana');
  });

  it('falls back to the formatted string when there is no street number at all', () => {
    // A blank line 1 under a dropped pin reads as "the map failed", so it never blanks.
    const parsed = addressFromGeocode([component('Kajang', ['locality'])], 'Kajang, Selangor');
    expect(parsed.line1).toBe('Kajang');
  });

  it('falls back to the district when Google names no locality', () => {
    const parsed = addressFromGeocode(
      [component('Hulu Langat', ['administrative_area_level_2'])],
      'Hulu Langat',
    );
    expect(parsed.city).toBe('Hulu Langat');
  });

  it('defaults the country rather than leaving it blank', () => {
    expect(addressFromGeocode([], 'somewhere').country).toBe('Malaysia');
  });
});

describe('composeSiteAddress', () => {
  it('matches the order the server composes in', () => {
    expect(
      composeSiteAddress({
        line1: '5 Jalan Impiana 1A',
        line2: 'Taman Bukit Impiana',
        postcode: '43000',
        city: 'Kajang',
        state: 'Selangor',
        country: 'Malaysia',
      }),
    ).toBe('5 Jalan Impiana 1A, Taman Bukit Impiana, 43000 Kajang, Selangor, Malaysia');
  });

  it('drops the parts nobody filled instead of leaving empty commas', () => {
    expect(
      composeSiteAddress({ ...EMPTY_SITE_ADDRESS, line1: '5 Jalan Impiana 1A', city: 'Kajang' }),
    ).toBe('5 Jalan Impiana 1A, Kajang, Malaysia');
  });

  it('is empty when nothing was entered, so the server can tell', () => {
    expect(composeSiteAddress({ ...EMPTY_SITE_ADDRESS, country: '' })).toBe('');
  });
});

describe('SitePicker without a key', () => {
  it('still renders every field, so a tenant with no map can still be dispatched to', () => {
    // The pin never blocks (AC-M38). No key is a configuration state, not an outage.
    render(
      <SitePicker
        address={EMPTY_SITE_ADDRESS}
        onAddress={() => {}}
        coords={null}
        onCoords={() => {}}
        apiKey={null}
      />,
    );
    expect(screen.getByText('Address line 1')).toBeInTheDocument();
    expect(screen.getByText('Postcode')).toBeInTheDocument();
    expect(screen.getByText('State')).toBeInTheDocument();
  });

  it('covers every state and federal territory', () => {
    // A free-text state produces "Selangor", "selangor" and "SGR" in one column and no
    // report can group them.
    expect(MALAYSIAN_STATES).toHaveLength(16);
    expect(MALAYSIAN_STATES).toContain('Selangor');
    expect(MALAYSIAN_STATES).toContain('W.P. Kuala Lumpur');
  });
});

describe('the map that hung on a spinner', () => {
  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).google;
    delete (window as unknown as Record<string, unknown>).__sorentoMapsLoader__;
  });

  function fakeMaps() {
    class Fake {
      setCenter() {}
      setPosition() {}
      setZoom() {}
      addListener() {}
    }
    return {
      Map: Fake,
      Marker: Fake,
      Geocoder: Fake,
      places: { AutocompleteService: Fake, AutocompleteSessionToken: Fake },
    };
  }

  function renderWithKey() {
    return render(
      <SitePicker
        address={EMPTY_SITE_ADDRESS}
        onAddress={() => {}}
        coords={null}
        onCoords={() => {}}
        apiKey="test-key"
      />,
    );
  }

  it('builds the map once the script is in, instead of spinning forever', async () => {
    // The bug: the build effect was keyed on `mapState`, which it also set. Setting
    // 'loading' changed a dependency, so React ran the cleanup for the in-flight attempt
    // (`cancelled = true`) and re-ran the effect, which bailed because the state was no
    // longer 'idle'. When the script arrived, the only attempt that could have built the
    // map had been told to stand down. Nothing errored - the spinner just never stopped.
    //
    // Maps already being on `window` is the fast path through the loader, so this exercises
    // exactly the resolve-then-build sequence the race lost.
    (window as unknown as { google: unknown }).google = { maps: fakeMaps() };
    renderWithKey();
    expect(screen.getByTestId('site-map-spinner')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('site-map-spinner')).toBeNull());
  });

  it('gives up visibly when the script cannot be fetched at all', async () => {
    // A restricted key, a blocked host or an offline phone. The consumer must be told the
    // address alone is enough, not left under a spinner - the pin never blocks (AC-M38).
    const appendChild = document.head.appendChild.bind(document.head);
    const spy = vi
      .spyOn(document.head, 'appendChild')
      .mockImplementation((node: unknown) => {
        const el = node as HTMLScriptElement;
        if (el.tagName === 'SCRIPT' && el.src.includes('maps.googleapis.com')) {
          setTimeout(() => el.onerror?.(new Event('error')), 0);
          return el as never;
        }
        return appendChild(node as never) as never;
      });
    try {
      renderWithKey();
      await waitFor(() =>
        expect(
          screen.getByText('The map could not load. The address above is enough.'),
        ).toBeInTheDocument(),
      );
      expect(screen.queryByTestId('site-map-spinner')).toBeNull();
    } finally {
      spy.mockRestore();
    }
  });
});

describe('a pin that moves and says nothing', () => {
  /**
   * The behaviour this replaces: the reverse geocode filled only fields that were still
   * EMPTY. So the first drop populated the form and every drop after it did nothing at
   * all - no fill, no message, no way to tell whether the map had understood the new
   * position. Moving a pin and seeing nothing happen reads as broken.
   */
  it('treats a form nobody has typed into as safe to fill outright', () => {
    expect(isAddressBlank(EMPTY_SITE_ADDRESS)).toBe(true);
  });

  it('treats a single typed field as somebody having answered', () => {
    // Their answer, not ours to replace. Anything typed means the proposal has to ask.
    expect(isAddressBlank({ ...EMPTY_SITE_ADDRESS, city: 'Kajang' })).toBe(false);
    expect(isAddressBlank({ ...EMPTY_SITE_ADDRESS, postcode: '43000' })).toBe(false);
  });

  it('does not count the defaulted country as an answer', () => {
    // 'Malaysia' is prefilled by the form itself, so counting it would mean the very first
    // pin drop always had to ask - the one case where asking is pure friction.
    expect(isAddressBlank({ ...EMPTY_SITE_ADDRESS, country: 'Malaysia' })).toBe(true);
  });
});

describe('changedFields', () => {
  const CURRENT = {
    line1: '5 Jalan Impiana 1A',
    line2: '',
    postcode: '43000',
    city: 'Kajang',
    state: 'Selangor',
    country: 'Malaysia',
  };

  it('names the fields a proposal would actually change', () => {
    // "Use this address?" over a one-line summary asks somebody to diff two addresses in
    // their head. Naming what moves makes it a decision.
    expect(
      changedFields(CURRENT, { line1: '7 Jalan Impiana 1A', postcode: '43000' }),
    ).toEqual(['Address line 1']);
  });

  it('counts filling a blank field as a change', () => {
    expect(changedFields(CURRENT, { line2: 'Taman Bukit Impiana' })).toEqual([
      'Address line 2',
    ]);
  });

  it('ignores a proposal that offers nothing for a field', () => {
    // A geocode with no postcode must not read as "this would clear your postcode".
    expect(changedFields(CURRENT, { postcode: '', city: '' })).toEqual([]);
  });

  it('is empty when the pin agrees with what is typed', () => {
    // Which is what lets the panel say "this matches" instead of offering a pointless
    // button.
    expect(changedFields(CURRENT, { ...CURRENT })).toEqual([]);
  });

  it('is not fooled by surrounding whitespace', () => {
    expect(changedFields(CURRENT, { city: '  Kajang  ' })).toEqual([]);
  });
});

describe('a listener registered once, on a form that keeps changing', () => {
  /**
   * The map's `click` and `dragend` handlers are attached ONCE, when the map is built, so
   * they hold the closure from that first render - where the address is still empty.
   * Reading `address` directly from them meant every pin move after the first still
   * believed the form was blank and auto-applied over answers the consumer had already
   * given, instead of asking.
   *
   * Found in a live walk: searching for an address filled the fields, and the very next
   * pin drop silently replaced them. This drives the same sequence through the real map
   * listener, which is the only way the stale closure is reachable.
   */
  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).google;
    delete (window as unknown as Record<string, unknown>).__sorentoMapsLoader__;
  });

  function mapsWithCapturedListeners(listeners: Record<string, (arg: unknown) => void>) {
    class FakeMap {
      setCenter() {}
      setZoom() {}
      addListener(event: string, handler: (arg: unknown) => void) {
        listeners[event] = handler;
      }
    }
    class FakeMarker {
      setPosition() {}
      getPosition() {
        return { lat: () => 3.1, lng: () => 101.6 };
      }
      addListener() {}
    }
    // A different street each call, because moving a pin to a different place is the
    // scenario: an identical result would correctly render "this matches" and prove
    // nothing about the closure.
    let call = 0;
    class FakeGeocoder {
      geocode(_request: unknown, callback: (results: unknown[], status: string) => void) {
        call += 1;
        const street = call === 1 ? 'Jalan Satu' : 'Jalan Dua';
        callback(
          [
            {
              formatted_address: `${call} ${street}, 43000 Kajang, Selangor, Malaysia`,
              address_components: [
                { long_name: String(call), short_name: String(call), types: ['street_number'] },
                { long_name: street, short_name: street, types: ['route'] },
                { long_name: 'Kajang', short_name: 'Kajang', types: ['locality'] },
              ],
            },
          ],
          'OK',
        );
      }
    }
    return { Map: FakeMap, Marker: FakeMarker, Geocoder: FakeGeocoder, places: {} };
  }

  it('asks before overwriting an address the consumer already has', async () => {
    const listeners: Record<string, (arg: unknown) => void> = {};
    (window as unknown as { google: unknown }).google = {
      maps: mapsWithCapturedListeners(listeners),
    };

    // A stateful host, exactly like the lodge flow: the pin's first fill has to be visible
    // to the pin's second.
    function Host() {
      const [address, setAddress] = useState(EMPTY_SITE_ADDRESS);
      return (
        <SitePicker
          address={address}
          onAddress={setAddress}
          coords={null}
          onCoords={() => {}}
          apiKey="test-key"
        />
      );
    }
    render(<Host />);
    await waitFor(() => expect(listeners.click).toBeTypeOf('function'));

    const tap = () =>
      act(() => {
        listeners.click({ latLng: { lat: () => 3.1, lng: () => 101.6 } });
      });

    // First tap: nothing typed, so filling outright is right and asking would be friction.
    tap();
    await screen.findByText(/We filled in the address above/);

    // Second tap: there IS an address now - the one the first tap wrote - so this must ask.
    tap();
    expect(
      await screen.findByRole('button', { name: 'Use this address' }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/We filled in the address above/)).toBeNull();
  });
});

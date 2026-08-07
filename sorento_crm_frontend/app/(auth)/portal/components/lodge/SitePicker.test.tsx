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
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import {
  EMPTY_SITE_ADDRESS,
  MALAYSIAN_STATES,
  SitePicker,
  addressFromGeocode,
  composeSiteAddress,
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

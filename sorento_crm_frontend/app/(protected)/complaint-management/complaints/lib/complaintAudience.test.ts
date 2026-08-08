/**
 * The rule that decides which complaint you are looking at.
 *
 * Kept out of the components so the detail page, the edit form and the list cannot drift
 * apart about what a complaint is - which is exactly what three copies of the same
 * conditional would do. That makes this the one place worth testing hard.
 */
import { describe, expect, it } from 'vitest';

import {
  complaintAudience,
  formatPin,
  isRetailComplaint,
  pinMapsUrl,
  reportedByLabel,
  siteAddressLines,
} from './complaintAudience';

describe('complaintAudience', () => {
  it('reads a portal-lodged complaint as retail', () => {
    expect(complaintAudience({ reported_by_role: 'end_user' })).toBe('retail');
  });

  it('reads a dealer report as retail, because it is about a thing somebody owns', () => {
    // A dealer reporting for a walk-in customer has a Site and a receipt, not a DO
    // number and a project title.
    expect(complaintAudience({ reported_by_role: 'dealer' })).toBe('retail');
  });

  it.each(['salesperson', 'cs', 'technician'])(
    'reads an internal reporter (%s) as project',
    (role) => {
      expect(complaintAudience({ reported_by_role: role })).toBe('project');
    },
  );

  it('reads a row that predates the column as project', () => {
    // Null is every complaint in the existing book of work. Those rows carry DO numbers
    // and project titles, so defaulting them to retail would blank the fields they use.
    expect(complaintAudience({ reported_by_role: null })).toBe('project');
    expect(complaintAudience({})).toBe('project');
    expect(complaintAudience(undefined)).toBe('project');
  });

  it('is not fooled by whitespace', () => {
    expect(isRetailComplaint({ reported_by_role: '  end_user  ' })).toBe(true);
  });
});

describe('reportedByLabel', () => {
  it('names each role the way staff say it', () => {
    expect(reportedByLabel('end_user')).toBe('End user');
    expect(reportedByLabel('cs')).toBe('Customer service');
  });

  it('shows an unknown role as itself rather than swallowing it', () => {
    // A role reaching the UI without a label is vocabulary drift worth seeing.
    expect(reportedByLabel('installer')).toBe('installer');
  });

  it('is nothing when there is no role', () => {
    expect(reportedByLabel(null)).toBeNull();
    expect(reportedByLabel('   ')).toBeNull();
  });
});

describe('siteAddressLines', () => {
  it('assembles the parts, with the postcode beside the city', () => {
    expect(
      siteAddressLines({
        site_address_line1: '5 Jalan Impiana 1A',
        site_address_line2: 'Taman Bukit Impiana',
        site_postcode: '43000',
        site_city: 'Kajang',
        site_state: 'Selangor',
        site_country: 'Malaysia',
      }),
    ).toEqual([
      '5 Jalan Impiana 1A',
      'Taman Bukit Impiana',
      '43000 Kajang',
      'Selangor',
      'Malaysia',
    ]);
  });

  it('drops the parts nobody filled instead of leaving blank rows', () => {
    expect(
      siteAddressLines({ site_address_line1: '5 Jalan Impiana 1A', site_city: 'Kajang' }),
    ).toEqual(['5 Jalan Impiana 1A', 'Kajang']);
  });

  it('falls back to the composed line when the parts are empty', () => {
    // Rows written before the parts existed have only the composed address, and showing
    // nothing for them would read as "no site".
    expect(siteAddressLines({ site_address: 'Kajang, Selangor' })).toEqual([
      'Kajang, Selangor',
    ]);
  });

  it('is empty when there is genuinely no address', () => {
    expect(siteAddressLines({})).toEqual([]);
  });
});

describe('formatPin', () => {
  it('formats a coordinate pair', () => {
    expect(formatPin('3.1184313', '101.6020993')).toBe('3.11843, 101.60210');
  });

  it('accepts numbers as well as the strings the API sends', () => {
    // The backend serializes a Decimal, so a coordinate arrives as a string and does not
    // round-trip through a float.
    expect(formatPin(3.1184313, 101.6020993)).toBe('3.11843, 101.60210');
  });

  it('is nothing when there is no pin', () => {
    expect(formatPin(null, null)).toBeNull();
    expect(formatPin(undefined, undefined)).toBeNull();
  });

  it('treats an empty string as no pin, not as the equator', () => {
    // Number('') is 0, which would drop a pin in the Atlantic and look like real data.
    expect(formatPin('', '')).toBeNull();
    expect(formatPin('3.11', '')).toBeNull();
  });

  it('refuses a half pin', () => {
    expect(formatPin('3.1184313', null)).toBeNull();
    expect(formatPin(null, '101.6')).toBeNull();
  });

  it('refuses a value that is not a number', () => {
    expect(formatPin('north', 'east')).toBeNull();
  });

  it('keeps a genuine zero', () => {
    expect(formatPin(0, 0)).toBe('0.00000, 0.00000');
  });
});

describe('pinMapsUrl', () => {
  it('builds a link a dispatcher can open without copying digits', () => {
    expect(pinMapsUrl('3.1184313', '101.6020993')).toBe(
      'https://www.google.com/maps/search/?api=1&query=3.11843%2C101.60210',
    );
  });

  it('is nothing without a pin', () => {
    expect(pinMapsUrl(null, null)).toBeNull();
  });
});

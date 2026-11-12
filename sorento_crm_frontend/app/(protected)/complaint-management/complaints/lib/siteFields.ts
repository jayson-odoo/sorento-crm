/** The complaint's Site, in the one order the detail card and the edit form both show. */
export const SITE_FIELDS = [
  { key: 'site_address_line1', label: 'Address line 1' },
  { key: 'site_address_line2', label: 'Address line 2' },
  { key: 'site_postcode', label: 'Postcode' },
  { key: 'site_city', label: 'City' },
  { key: 'site_state', label: 'State' },
  { key: 'site_country', label: 'Country' },
  { key: 'site_contact_name', label: 'Contact on site' },
  { key: 'site_contact_phone', label: 'Contact phone' },
] as const;

export type SiteFieldKey = (typeof SITE_FIELDS)[number]['key'];

export const SITE_KEYS: SiteFieldKey[] = SITE_FIELDS.map((f) => f.key);

import { describe, expect, it } from 'vitest';
import { draftToPayload, toDraft } from './themeDraft';

describe('themeDraft', () => {
  it('toDraft turns null/undefined theme fields into blank strings', () => {
    const draft = toDraft({
      logo_url: null,
      primary_color: '#123456',
      social_links: null,
    });

    expect(draft.logo_url).toBe('');
    expect(draft.primary_color).toBe('#123456');
    expect(draft.social_links).toEqual([]);
  });

  it('draftToPayload saves a blank field as null (D1, AC-EM021)', () => {
    const draft = toDraft(null);
    draft.company_name = '  ';
    draft.logo_height = '';
    draft.button_radius = '  ';

    const payload = draftToPayload(draft);

    expect(payload.company_name).toBeNull();
    expect(payload.logo_height).toBeNull();
    expect(payload.button_radius).toBeNull();
  });

  it('draftToPayload keeps a real value, trimmed, and numbers as numbers', () => {
    const draft = toDraft(null);
    draft.company_name = '  Sorento  ';
    draft.logo_height = '48';
    draft.primary_color = '#2563EB';

    const payload = draftToPayload(draft);

    expect(payload.company_name).toBe('Sorento');
    expect(payload.logo_height).toBe(48);
    expect(payload.primary_color).toBe('#2563EB');
  });

  it('draftToPayload drops a social link row where both fields are blank, keeps a real one', () => {
    const draft = toDraft(null);
    draft.social_links = [
      { label: '', url: '' },
      { label: 'LinkedIn', url: 'https://linkedin.com/company/sorento' },
    ];

    const payload = draftToPayload(draft);

    expect(payload.social_links).toEqual([
      { label: 'LinkedIn', url: 'https://linkedin.com/company/sorento' },
    ]);
  });

  it('draftToPayload sends null social_links when every row is blank', () => {
    const draft = toDraft(null);
    draft.social_links = [{ label: '', url: '' }];

    const payload = draftToPayload(draft);

    expect(payload.social_links).toBeNull();
  });
});

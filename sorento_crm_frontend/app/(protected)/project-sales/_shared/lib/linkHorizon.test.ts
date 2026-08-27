/**
 * The link horizon's own rules (`PLAN-scm-oi-handshake.md` section 11, AC-LH1/AC-LH5).
 *
 * Four presses share this helper - Acknowledge, Link selected, Link now and Auto-link -
 * and the page's date input, the URL and this browser's memory all feed it. The three
 * answers it has to keep apart are a DATE, NO horizon at all, and nothing said (which the
 * server reads as the reorder plan's own): the middle one used to travel as the last one,
 * so a buyer who emptied the box got the plan's date back and could not link a far-future
 * row at all.
 *
 * Written per item 7 of the 27 August re-review, which found the whole file untested.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import {
  LINK_HORIZON_STORAGE_KEY,
  NO_LINK_HORIZON,
  formatHorizon,
  horizonLabel,
  horizonSentence,
  initialLinkHorizon,
  isDueAfterHorizon,
  isHorizonDate,
  linkHorizonRequest,
  readStoredLinkHorizon,
  readUrlLinkHorizon,
  startsCleared,
  storeLinkHorizon,
} from './linkHorizon';

const HORIZON = '2026-12-31';

describe('linkHorizonRequest', () => {
  it('sends the date when there is one', () => {
    expect(linkHorizonRequest(HORIZON, false)).toEqual({ link_up_to: HORIZON });
  });

  it('sends the date even if the cleared flag was left standing behind it', () => {
    // The page sets the date and the flag together, but the date is the buyer's latest
    // word either way and a request that carried both would be a 422 on the server.
    expect(linkHorizonRequest(HORIZON, true)).toEqual({ link_up_to: HORIZON });
  });

  it('says "no horizon" OUT LOUD when the buyer cleared the box', () => {
    // Silence means "take the plan's own date", which is the opposite of what emptying
    // the box says.
    expect(linkHorizonRequest('', true)).toEqual({ link_horizon: NO_LINK_HORIZON });
  });

  it('says nothing when nobody has ever chosen, and the server takes the plan', () => {
    expect(linkHorizonRequest('', false)).toEqual({});
  });

  it('ignores a value that is not a plain date rather than half-parsing it', () => {
    expect(linkHorizonRequest('next month', false)).toEqual({});
    expect(linkHorizonRequest('2026-12-31T00:00:00', false)).toEqual({});
  });
});

describe('startsCleared', () => {
  it('is false when nobody has said anything', () => {
    expect(startsCleared(null, null)).toBe(false);
  });

  it('is true when this browser remembers the buyer taking the horizon off', () => {
    expect(startsCleared(null, NO_LINK_HORIZON)).toBe(true);
  });

  it('is false when this browser remembers a date', () => {
    expect(startsCleared(null, HORIZON)).toBe(false);
  });

  it('is false when the URL names a date, whatever this browser remembers', () => {
    expect(startsCleared('2027-06-30', NO_LINK_HORIZON)).toBe(false);
  });

  it('is true when the URL itself says no horizon, over a remembered date', () => {
    // AC-LH5: the URL is what the buttons send, and that has to hold for the CLEARED
    // state too or a shared link means something different in the other browser.
    expect(startsCleared(NO_LINK_HORIZON, HORIZON)).toBe(true);
  });
});

describe('horizonLabel and horizonSentence', () => {
  it('reads the date the way the rest of the page reads dates', () => {
    expect(horizonLabel(HORIZON, false)).toBe('31/12/2026');
    expect(horizonSentence(HORIZON, false)).toBe('Link up to 31/12/2026');
  });

  it('is ONE phrase when the horizon is off, never "Link up to No horizon"', () => {
    expect(horizonLabel('', true)).toBe('No horizon');
    expect(horizonSentence('', true)).toBe('No link horizon');
  });

  it('says nothing at all when nobody has chosen', () => {
    expect(horizonLabel('', false)).toBe('');
    expect(horizonSentence('', false)).toBe('');
  });
});

describe('what this browser remembers', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('remembers a date', () => {
    storeLinkHorizon(HORIZON);
    expect(window.localStorage.getItem(LINK_HORIZON_STORAGE_KEY)).toBe(HORIZON);
    expect(readStoredLinkHorizon()).toBe(HORIZON);
  });

  it('remembers "no horizon" as its own marker, not as an absent key', () => {
    storeLinkHorizon(NO_LINK_HORIZON);
    expect(readStoredLinkHorizon()).toBe(NO_LINK_HORIZON);
  });

  it('FORGETS on null, which is the only thing that means "has not said"', () => {
    storeLinkHorizon(HORIZON);
    storeLinkHorizon(null);
    expect(window.localStorage.getItem(LINK_HORIZON_STORAGE_KEY)).toBeNull();
    expect(readStoredLinkHorizon()).toBeNull();
  });

  it('reads a value in any other shape as never having chosen', () => {
    window.localStorage.setItem(LINK_HORIZON_STORAGE_KEY, 'whenever');
    expect(readStoredLinkHorizon()).toBeNull();
  });
});

describe('what the URL says about the horizon', () => {
  it('reads a date off ?link_up_to=', () => {
    expect(readUrlLinkHorizon(new URLSearchParams(`link_up_to=${HORIZON}`))).toBe(HORIZON);
  });

  it('reads a cleared horizon off ?link_horizon=none', () => {
    expect(readUrlLinkHorizon(new URLSearchParams('link_horizon=none'))).toBe(
      NO_LINK_HORIZON,
    );
  });

  it('takes the date when a link carries both, because a date is the more exact word', () => {
    expect(
      readUrlLinkHorizon(new URLSearchParams(`link_up_to=${HORIZON}&link_horizon=none`)),
    ).toBe(HORIZON);
  });

  it('says nothing for a URL that names neither, or a mode it does not know', () => {
    expect(readUrlLinkHorizon(new URLSearchParams(''))).toBeNull();
    expect(readUrlLinkHorizon(new URLSearchParams('link_horizon=plan'))).toBeNull();
    expect(readUrlLinkHorizon(null)).toBeNull();
  });
});

describe('the precedence: the URL, then this browser, then the plan', () => {
  it("starts at the plan's own horizon when nobody else has said", () => {
    expect(initialLinkHorizon(null, null, HORIZON)).toBe(HORIZON);
  });

  it('takes a date in the URL over this browser and over the plan', () => {
    expect(initialLinkHorizon('2027-06-30', HORIZON, '2028-01-01')).toBe('2027-06-30');
  });

  it('takes this browser over the plan', () => {
    expect(initialLinkHorizon(null, '2027-06-30', HORIZON)).toBe('2027-06-30');
  });

  it('starts BLANK when this browser remembers no horizon, plan default and all', () => {
    expect(initialLinkHorizon(null, NO_LINK_HORIZON, HORIZON)).toBe('');
  });

  it('starts blank when the URL itself says no horizon, over a remembered date', () => {
    expect(initialLinkHorizon(NO_LINK_HORIZON, '2027-06-30', HORIZON)).toBe('');
  });

  it('is blank when none of the three has one', () => {
    expect(initialLinkHorizon(null, null, null)).toBe('');
  });
});

describe('the small readers everything else leans on', () => {
  it('accepts a plain date and nothing else', () => {
    expect(isHorizonDate(HORIZON)).toBe(true);
    expect(isHorizonDate('31/12/2026')).toBe(false);
    expect(isHorizonDate(null)).toBe(false);
  });

  it('formats only what it can read', () => {
    expect(formatHorizon(HORIZON)).toBe('31/12/2026');
    expect(formatHorizon(NO_LINK_HORIZON)).toBe('');
  });

  it('holds a row back only when it is due AFTER a stated horizon', () => {
    expect(isDueAfterHorizon('2030-01-01', HORIZON)).toBe(true);
    expect(isDueAfterHorizon('2026-10-01', HORIZON)).toBe(false);
    // AC-LH4: a row nobody has dated is INSIDE the horizon, never held back for a date
    // that was never stated.
    expect(isDueAfterHorizon(null, HORIZON)).toBe(false);
    expect(isDueAfterHorizon('2030-01-01', '')).toBe(false);
  });
});

import { describe, expect, it } from 'vitest';
import { dateAnswerProblem, dateAnswerText, shownDeliveryDate } from './sample-request-tracking';

const fmt = (iso: string) => `D(${iso})`;

describe('shownDeliveryDate', () => {
  it('shows the requested date when the team can meet it or has not answered', () => {
    const base = { delivery_date: '2026-12-01', proposed_delivery_date: null };
    expect(shownDeliveryDate({ ...base, date_feasible: true })).toEqual({
      date: '2026-12-01',
      isNew: false,
    });
    expect(shownDeliveryDate({ ...base, date_feasible: null })).toEqual({
      date: '2026-12-01',
      isNew: false,
    });
  });

  it('shows the proposed date, flagged new, when the team cannot meet it', () => {
    expect(
      shownDeliveryDate({
        delivery_date: '2026-12-01',
        date_feasible: false,
        proposed_delivery_date: '2026-12-09',
      }),
    ).toEqual({ date: '2026-12-09', isNew: true });
  });
});

describe('dateAnswerText', () => {
  it('reads each answer', () => {
    expect(dateAnswerText({ date_feasible: true, proposed_delivery_date: null }, fmt)).toBe(
      'Can meet the requested date',
    );
    expect(
      dateAnswerText({ date_feasible: false, proposed_delivery_date: '2026-12-09' }, fmt),
    ).toBe('Proposes D(2026-12-09)');
    expect(dateAnswerText({ date_feasible: null, proposed_delivery_date: null }, fmt)).toBeNull();
  });
});

describe('dateAnswerProblem', () => {
  const today = '2026-11-02';
  it('needs an answer', () => {
    expect(dateAnswerProblem(null, '', today)).toMatch(/Say whether/);
  });
  it('accepts yes with no date', () => {
    expect(dateAnswerProblem(true, '', today)).toBeNull();
  });
  it('needs a proposed date on no, today or later', () => {
    expect(dateAnswerProblem(false, '', today)).toMatch(/Enter the date/);
    expect(dateAnswerProblem(false, '2026-11-01', today)).toMatch(/past/);
    expect(dateAnswerProblem(false, today, today)).toBeNull();
  });
});

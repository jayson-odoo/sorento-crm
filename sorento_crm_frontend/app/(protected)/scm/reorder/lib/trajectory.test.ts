import { describe, expect, it } from 'vitest';
import {
  TRAJECTORY_ROW_LABEL,
  chartSeries,
  describeTrajectory,
  describeYearAgo,
  trajectoryKey,
  type TrajectoryEntry,
} from './trajectory';

/**
 * The wording over the trajectory verdicts (S13d).
 *
 * Two rules under test: the row states the ACTION, never a bare percentage (AC-S13d.3),
 * and the year-ago comparison is named absent rather than read as zero.
 */

const entry = (over: Partial<TrajectoryEntry> = {}): TrajectoryEntry => ({
  verdict: 'rising',
  recent_qty: 120,
  previous_qty: 90,
  change_pct: 33.33,
  year_ago_qty: 200,
  year_change_pct: -40,
  window_months: 12,
  months: [],
  customers: [],
  agents: [],
  agents_available: false,
  ...over,
});

describe('the row label', () => {
  it('states the action, not a percentage', () => {
    for (const label of Object.values(TRAJECTORY_ROW_LABEL)) {
      expect(label).not.toMatch(/%|\d/);
    }
    expect(TRAJECTORY_ROW_LABEL.rising).toBe('Orders rising - consider more');
    expect(TRAJECTORY_ROW_LABEL.quiet).toBe('No recent orders - buy just enough');
  });
});

describe('describeTrajectory', () => {
  it('leads with the two window totals, in words a person says', () => {
    expect(describeTrajectory(entry())).toBe(
      'Orders are rising: 120 ordered in the last 12 months, 90 in the 12 months before. Worth considering more than the bare need.',
    );
  });

  it('tells a quiet product to buy just enough', () => {
    const text = describeTrajectory(entry({ verdict: 'quiet', recent_qty: 0 }));

    expect(text).toMatch(/orders stopped/i);
    expect(text).toMatch(/buy just enough/i);
  });

  it('says never ordered rather than implying a heyday that never happened', () => {
    const text = describeTrajectory(
      entry({ verdict: 'no_history', recent_qty: 0, previous_qty: 0 }),
    );

    expect(text).toMatch(/no orders on record/i);
  });

  it('has no opinion without facts', () => {
    expect(describeTrajectory(undefined)).toMatch(/no order information/i);
  });
});

describe('describeYearAgo', () => {
  it('gives the year-ago comparison beside the verdict', () => {
    expect(describeYearAgo(entry())).toBe(
      'Against the same window last year (200): down 40%.',
    );
  });

  it('names the absence when the book is younger than a year', () => {
    expect(describeYearAgo(entry({ year_ago_qty: null, year_change_pct: null }))).toBe(
      'No figure for the same window last year.',
    );
  });
});

describe('trajectoryKey', () => {
  it('defaults an unsegmented warehouse to project, exactly as the service does', () => {
    expect(trajectoryKey('p1', 'dealer')).toBe('p1:dealer');
    expect(trajectoryKey('p1', null)).toBe('p1:project');
    expect(trajectoryKey(null, 'dealer')).toBeNull();
  });
});

describe('chartSeries', () => {
  it('pairs each recent month with the SAME month a year earlier', () => {
    const now = new Date();
    const m = (offset: number) => {
      const d = new Date(now.getFullYear(), now.getMonth() - 1 - offset, 1);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    };
    const t = entry({
      months: [
        { month: m(0), qty: 60 },
        { month: m(12), qty: 25 },
      ],
    });

    const { thisYear, lastYear } = chartSeries(t);

    expect(thisYear[11]).toBe(60);
    expect(lastYear[11]).toBe(25);
  });

  it('renders a missing year-ago month as null, never as a zero the chart draws', () => {
    const { lastYear } = chartSeries(entry({ months: [] }));

    expect(lastYear.every((v) => v === null)).toBe(true);
  });
});

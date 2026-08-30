'use client';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { DateRangePicker } from '@/components/ui/date-range-picker';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import type {
  ReportParamMeta,
  ReportParamValue,
  ReportParamValues,
  ReportPeriod,
} from '@/services/reportService';

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

const MONTH_CHIPS = MONTHS.map((label) => label.slice(0, 3));

const PERIOD_KIND_OPTIONS = [
  { value: 'month_range', label: 'Month range' },
  { value: 'custom', label: 'Custom dates' },
];

function asPeriod(value: ReportParamValue | undefined, fallback: ReportPeriod): ReportPeriod {
  if (value && typeof value === 'object' && !Array.isArray(value) && 'kind' in value) {
    return value as ReportPeriod;
  }
  return fallback;
}

/** This year where the users are, which is the year the report opens on. */
function malaysiaYear(): number {
  return Number(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kuala_Lumpur',
      year: 'numeric',
    }).format(new Date()),
  );
}

/**
 * The years the Period control offers.
 *
 * The dataset's own years are not enough: on 1 January nothing has been filed in the new
 * year yet, so `years` would not hold it and the control the report is OPEN on would
 * render blank. The year in hand and the default year are always offerable, whether or
 * not a row is dated in them.
 */
function yearOptions(available: number[], ...alsoOffer: (number | undefined)[]): number[] {
  const years = new Set<number>(available);
  years.add(malaysiaYear());
  for (const year of alsoOffer) if (year) years.add(year);
  return [...years].sort((a, b) => b - a);
}

/**
 * The month chips: All, Jan .. Dec, under the Period control (AC-G1).
 *
 * The workbook this report mirrors is twelve monthly sheets, so a month is the unit the
 * team actually works in and it has to be ONE click, not three controls. A chip is a
 * `month_range` period whose ends are the same month - a shape the engine, the sheet
 * naming and the export already understand - so a single-month export comes out as SUMMARY
 * plus that one sheet with nothing added to the wire.
 *
 * They appear over a year and over a single month, which are the two states they can move
 * between, and stay out of the way of a real range or a custom date span.
 */
function MonthChips({
  period,
  onPick,
  disabled,
}: {
  period: ReportPeriod;
  onPick: (period: ReportPeriod) => void;
  disabled: boolean;
}) {
  const single =
    period.kind === 'month_range' && period.from_month === period.to_month
      ? period.from_month
      : null;
  if (period.kind === 'custom' || (period.kind === 'month_range' && single === null)) return null;

  const year = period.year;
  const chip = (label: string, active: boolean, next: ReportPeriod) => (
    <Button
      key={label}
      type="button"
      size="sm"
      variant={active ? 'primary' : 'outline'}
      aria-pressed={active}
      disabled={disabled}
      className="h-7 px-2.5"
      onClick={() => onPick(next)}
    >
      {label}
    </Button>
  );

  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Month">
      {chip('All', period.kind === 'year', { kind: 'year', year })}
      {MONTH_CHIPS.map((label, index) =>
        chip(label, single === index + 1, {
          kind: 'month_range',
          year,
          from_month: index + 1,
          to_month: index + 1,
        }),
      )}
    </div>
  );
}

/**
 * The report filter bar, rendered from `GET /reports/{key}` param meta - never from a
 * per-report component. A new report gets its filters by declaring params, which is what
 * makes report #2 cost two backend files (PLAN "Why a foundation and not a page").
 *
 * Wraps at 375px: every control is its own labelled block in a flex-wrap row.
 */
export function ReportFilterBar({
  params,
  values,
  onChange,
  disabled = false,
}: {
  params: ReportParamMeta[];
  values: ReportParamValues;
  onChange: (key: string, value: ReportParamValue) => void;
  disabled?: boolean;
}) {
  const periodParam = params.find((param) => param.kind === 'period');
  const currentPeriod =
    periodParam?.kind === 'period' ? asPeriod(values[periodParam.key], periodParam.default) : null;

  return (
    <div className="flex flex-wrap items-end gap-3">
      {params.map((param) => {
        if (param.kind === 'date_basis') {
          const value = typeof values[param.key] === 'string' ? (values[param.key] as string) : param.default;
          return (
            <div key={param.key} className="w-full sm:w-48">
              <Label htmlFor={`report-param-${param.key}`}>{param.label}</Label>
              <SearchableSelect
                id={`report-param-${param.key}`}
                value={value}
                onChange={(next) => onChange(param.key, next)}
                options={param.options}
                placeholder={param.label}
                triggerClassName="mt-1 w-full"
                disabled={disabled}
              />
            </div>
          );
        }

        if (param.kind === 'period') {
          const period = asPeriod(values[param.key], param.default);
          const years = yearOptions(
            param.years,
            param.default.kind === 'custom' ? undefined : param.default.year,
            period.kind === 'custom' ? undefined : period.year,
          );
          const fallbackYear = years[0] ?? malaysiaYear();
          const kindValue = period.kind === 'year' ? String(period.year) : period.kind;
          const yearChoices = years.map((year) => ({ value: String(year), label: String(year) }));
          const options = [...yearChoices, ...PERIOD_KIND_OPTIONS];
          return (
            <div key={param.key} className="flex w-full flex-wrap items-end gap-3 sm:w-auto">
              <div className="w-full sm:w-44">
                <Label htmlFor={`report-param-${param.key}`}>{param.label}</Label>
                <SearchableSelect
                  id={`report-param-${param.key}`}
                  value={kindValue}
                  onChange={(next) => {
                    if (next === 'month_range') {
                      const year = period.kind === 'custom' ? fallbackYear : (period as { year?: number }).year ?? fallbackYear;
                      onChange(param.key, { kind: 'month_range', year, from_month: 1, to_month: 12 });
                      return;
                    }
                    if (next === 'custom') {
                      const year = period.kind === 'custom' ? fallbackYear : (period as { year?: number }).year ?? fallbackYear;
                      onChange(param.key, {
                        kind: 'custom',
                        from: `${year}-01-01`,
                        to: `${year}-12-31`,
                      });
                      return;
                    }
                    onChange(param.key, { kind: 'year', year: Number(next) });
                  }}
                  options={options}
                  placeholder={param.label}
                  triggerClassName="mt-1 w-full"
                  disabled={disabled}
                />
              </div>

              {/* A chip and these three controls describe the SAME period, so they are
                  shown together and always agree: the chip says which month, and To is how
                  that month becomes Mar..Jun. Hidden while the range was one month, a
                  single month was a dead end - Period already read "Month range", so
                  re-picking it changed nothing (AC-G1). */}
              {period.kind === 'month_range' && (
                <>
                  <div className="w-full sm:w-32">
                    <Label htmlFor="report-param-period-year">Year</Label>
                    <SearchableSelect
                      id="report-param-period-year"
                      value={String(period.year)}
                      onChange={(next) => onChange(param.key, { ...period, year: Number(next) })}
                      options={yearChoices}
                      placeholder="Year"
                      triggerClassName="mt-1 w-full"
                      disabled={disabled}
                    />
                  </div>
                  <div className="w-full sm:w-36">
                    <Label htmlFor="report-param-period-from">From month</Label>
                    <SearchableSelect
                      id="report-param-period-from"
                      value={String(period.from_month)}
                      onChange={(next) =>
                        onChange(param.key, {
                          ...period,
                          from_month: Number(next),
                          to_month: Math.max(period.to_month, Number(next)),
                        })
                      }
                      options={MONTHS.map((label, index) => ({ value: String(index + 1), label }))}
                      placeholder="From"
                      triggerClassName="mt-1 w-full"
                      disabled={disabled}
                    />
                  </div>
                  <div className="w-full sm:w-36">
                    <Label htmlFor="report-param-period-to">To month</Label>
                    <SearchableSelect
                      id="report-param-period-to"
                      value={String(period.to_month)}
                      onChange={(next) =>
                        onChange(param.key, {
                          ...period,
                          to_month: Number(next),
                          from_month: Math.min(period.from_month, Number(next)),
                        })
                      }
                      options={MONTHS.map((label, index) => ({ value: String(index + 1), label }))}
                      placeholder="To"
                      triggerClassName="mt-1 w-full"
                      disabled={disabled}
                    />
                  </div>
                </>
              )}

              {period.kind === 'custom' && (
                <div className="w-full sm:w-72">
                  <Label htmlFor="report-param-period-range">Dates</Label>
                  {/* ONE control: a range is one fact, and two pickers let the user cross
                      the ends over before either is wrong (ADR-PRODUCT-STANDARDS 1c). */}
                  <DateRangePicker
                    id="report-param-period-range"
                    aria-label="Custom date range"
                    from={period.from}
                    to={period.to}
                    // A null end is an ANSWER: Clear empties both, and the first click of
                    // a two-click range carries a start alone. Mapping it back onto the
                    // previous value made Clear a no-op and could leave the old end BEFORE
                    // the new start, which the backend answers with a 422. An incomplete
                    // range is simply not run (`periodIsRunnable` in ReportPage).
                    onChange={(next) =>
                      onChange(param.key, {
                        kind: 'custom',
                        from: next.from ?? '',
                        to: next.to ?? '',
                      })
                    }
                    disabled={disabled}
                    className="mt-1"
                  />
                </div>
              )}
            </div>
          );
        }

        const selected = Array.isArray(values[param.key]) ? (values[param.key] as string[]) : [];
        if (param.multi) {
          return (
            <div key={param.key} className="w-full sm:w-64">
              <Label htmlFor={`report-param-${param.key}`}>{param.label}</Label>
              <SearchableMultiSelect
                id={`report-param-${param.key}`}
                value={selected}
                onChange={(next) => onChange(param.key, next)}
                options={param.options}
                placeholder="All"
                triggerClassName="mt-1 w-full"
                disabled={disabled}
              />
            </div>
          );
        }
        return (
          <div key={param.key} className="w-full sm:w-48">
            <Label htmlFor={`report-param-${param.key}`}>{param.label}</Label>
            <SearchableSelect
              id={`report-param-${param.key}`}
              value={selected[0] ?? ''}
              onChange={(next) => onChange(param.key, next ? [next] : [])}
              options={param.options}
              placeholder="All"
              triggerClassName="mt-1 w-full"
              clearable={param.clearable}
              disabled={disabled}
            />
          </div>
        );
      })}
      {/* `w-full` puts the chips on their own line of the wrapping row, under the controls
          they belong to, at 1280 and at 375 alike. */}
      {periodParam && currentPeriod && (
        <div className="w-full">
          <MonthChips
            period={currentPeriod}
            onPick={(next) => onChange(periodParam.key, next)}
            disabled={disabled}
          />
        </div>
      )}
    </div>
  );
}

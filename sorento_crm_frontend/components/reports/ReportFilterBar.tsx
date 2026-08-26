'use client';

import { Label } from '@/components/ui/label';
import { DatePicker } from '@/components/ui/date-picker';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { formatLocalDateToYyyyMmDd } from '@/lib/helpers';
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

function parseYyyyMmDd(value: string): Date | undefined {
  if (!value) return undefined;
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return undefined;
  return new Date(y, m - 1, d);
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
          const fallbackYear = param.years[0] ?? new Date().getFullYear();
          const kindValue = period.kind === 'year' ? String(period.year) : period.kind;
          const options = [
            ...param.years.map((year) => ({ value: String(year), label: String(year) })),
            ...PERIOD_KIND_OPTIONS,
          ];
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

              {period.kind === 'month_range' && (
                <>
                  <div className="w-full sm:w-32">
                    <Label htmlFor="report-param-period-year">Year</Label>
                    <SearchableSelect
                      id="report-param-period-year"
                      value={String(period.year)}
                      onChange={(next) => onChange(param.key, { ...period, year: Number(next) })}
                      options={param.years.map((year) => ({ value: String(year), label: String(year) }))}
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
                <>
                  <div className="w-full sm:w-44">
                    <Label htmlFor="report-param-period-start">From</Label>
                    <DatePicker
                      id="report-param-period-start"
                      value={parseYyyyMmDd(period.from)}
                      onChange={(date) =>
                        onChange(param.key, {
                          ...period,
                          from: date ? formatLocalDateToYyyyMmDd(date) : period.from,
                        })
                      }
                      disabled={disabled}
                      className="mt-1"
                      required
                    />
                  </div>
                  <div className="w-full sm:w-44">
                    <Label htmlFor="report-param-period-end">To</Label>
                    <DatePicker
                      id="report-param-period-end"
                      value={parseYyyyMmDd(period.to)}
                      onChange={(date) =>
                        onChange(param.key, {
                          ...period,
                          to: date ? formatLocalDateToYyyyMmDd(date) : period.to,
                        })
                      }
                      disabled={disabled}
                      className="mt-1"
                      required
                    />
                  </div>
                </>
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
    </div>
  );
}

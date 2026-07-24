import { describe, expect, it } from 'vitest';
import { mapFormToUpdateBody } from './mapFormToUpdateBody';
import type { ScheduledTask } from '../types/scheduledTask.types';
import type { FormValues } from '../components/ScheduledTaskForm';

const task: ScheduledTask = {
  id: 'task-1',
  key: 'system_health_watchdog',
  name: 'System health watchdog',
  description: null,
  enabled: true,
  interval_unit: 'minutes',
  interval_value: 10,
  timezone: 'UTC',
  start_at: null,
  next_run_at: null,
  last_run_at: null,
  last_status: null,
  last_error: null,
  metadata: { grace_percent: 50 },
  created_at: '2026-07-01T00:00:00',
  updated_at: '2026-07-01T00:00:00',
  due_at: null,
  grace_percent: 50,
  grace_seconds: 300,
  is_overdue: false,
  late_by_seconds: null,
};

const values: FormValues = {
  name: 'System health watchdog',
  description: '',
  enabled: true,
  interval_value: 10,
  interval_unit: 'minutes',
  timezone: 'UTC',
  start_at: null,
  grace_percent: '',
};

describe('mapFormToUpdateBody — grace override', () => {
  it('sends the numeric override when one is set', () => {
    const body = mapFormToUpdateBody({ ...values, grace_percent: 50 }, task);
    expect(body.metadata).toEqual({ grace_percent: 50 });
  });

  it('sends null (not an omitted key) when the field is cleared', () => {
    // The backend MERGES metadata and removes a key only on an explicit null.
    // Omitting the key silently leaves the stored override in place — the bug
    // this test exists to prevent.
    const body = mapFormToUpdateBody({ ...values, grace_percent: '' }, task);
    expect(body.metadata).toHaveProperty('grace_percent', null);
  });

  it('treats undefined the same as cleared', () => {
    const body = mapFormToUpdateBody({ ...values, grace_percent: undefined }, task);
    expect(body.metadata).toHaveProperty('grace_percent', null);
  });

  it('accepts 0 as a real value rather than treating it as blank', () => {
    const body = mapFormToUpdateBody({ ...values, grace_percent: 0 }, task);
    expect(body.metadata).toEqual({ grace_percent: 0 });
  });

  it('carries the sla digest channel keys alongside grace for that task', () => {
    const slaTask = { ...task, key: 'user_sla_daily_summary' };
    const body = mapFormToUpdateBody(
      { ...values, grace_percent: 30, send_in_app: false, send_email: true },
      slaTask,
    );
    expect(body.metadata).toEqual({
      send_in_app: false,
      send_email: true,
      grace_percent: 30,
    });
  });

  it('still maps the non-metadata config fields', () => {
    const body = mapFormToUpdateBody({ ...values, interval_value: 15 }, task);
    expect(body.interval_value).toBe(15);
    expect(body.interval_unit).toBe('minutes');
    expect(body.enabled).toBe(true);
    expect(body.start_at).toBeNull();
  });
});

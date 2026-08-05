import type { FormValues } from '../components/ScheduledTaskForm';
import type { ScheduledTask, ScheduledTaskUpdateBody } from '../types/scheduledTask.types';

/**
 * Build the PATCH body for a scheduled task.
 *
 * Metadata semantics are the backend's, and they are easy to get wrong:
 * `update_task` **merges** the submitted map into the stored one and removes a key
 * only when its value is explicitly `null`. Omitting a key leaves the stored value
 * untouched — so clearing the grace override requires sending `grace_percent: null`,
 * not an object without the key.
 */
export function mapFormToUpdateBody(
  values: FormValues,
  task: ScheduledTask,
): ScheduledTaskUpdateBody {
  const body: ScheduledTaskUpdateBody = {
    name: values.name,
    description: values.description ?? null,
    enabled: values.enabled,
    interval_value: values.interval_value,
    interval_unit: values.interval_unit,
    timezone: values.timezone,
    start_at: values.start_at ? values.start_at.toISOString() : null,
  };

  const metadata: Record<string, unknown> = {};

  // Companies this task may touch. Empty means every company, and null is the
  // backend's delete sentinel - persisting an empty ARRAY instead would leave a key
  // the scheduler has to special-case forever, so clear it properly.
  const companyIds = values.company_ids ?? [];
  metadata.company_ids = companyIds.length > 0 ? companyIds : null;

  if (task.key === 'user_sla_daily_summary') {
    metadata.send_in_app = values.send_in_app !== false;
    metadata.send_email = values.send_email !== false;
  }

  const grace = values.grace_percent;
  if (grace === '' || grace === undefined || grace === null) {
    // Blank means "use the global default". null is the backend's delete sentinel.
    metadata.grace_percent = null;
  } else {
    metadata.grace_percent = grace;
  }

  if (Object.keys(metadata).length > 0) body.metadata = metadata;
  return body;
}

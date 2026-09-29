import type { FormValues } from '../components/ScheduledTaskForm';
import type { ScheduledTask, ScheduledTaskUpdateBody } from '../types/scheduledTask.types';

/**
 * Build the PATCH body for a scheduled task.
 *
 * Metadata semantics are the backend's, and they are easy to get wrong:
 * `update_task` **merges** the submitted map into the stored one and removes a key
 * only when its value is explicitly `null`. Omitting a key leaves the stored value
 * untouched - so clearing the grace override requires sending `grace_percent: null`,
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

  // #1340: the scheduled reorder run's configurable scope. These seven keys only ride
  // the PATCH body for this task - every other task key must never carry them, same
  // rule as the SLA channel keys above.
  if (task.key === 'scm_reorder_run') {
    const warehouseCodes = values.warehouse_codes ?? [];
    metadata.warehouse_codes = warehouseCodes.length > 0 ? warehouseCodes : null;
    const productCodes = values.product_codes ?? [];
    metadata.product_codes = productCodes.length > 0 ? productCodes : null;
    metadata.demand_class = values.demand_class ? values.demand_class : null;
    metadata.horizon_start_days =
      values.horizon_start_days === '' || values.horizon_start_days === undefined
        ? null
        : values.horizon_start_days;
    metadata.horizon_end_days =
      values.horizon_end_days === '' || values.horizon_end_days === undefined
        ? null
        : values.horizon_end_days;
    metadata.budget = values.budget === '' || values.budget === undefined ? null : values.budget;
    // A plain boolean field (like send_in_app/send_email), not a blank-means-clear one -
    // false is a real value, not the delete sentinel.
    metadata.include_market = values.include_market === true;
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

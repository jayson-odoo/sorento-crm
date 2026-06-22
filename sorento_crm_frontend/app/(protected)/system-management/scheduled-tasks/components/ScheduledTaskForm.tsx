'use client';

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { ScheduledTask } from '../types/scheduledTask.types';
import { parseDateTimeAsUTC } from '@/lib/helpers';

/** Format a Date as a `datetime-local` value in the browser's local timezone.
 *  start_at is serialized to UTC on submit (Date.toISOString), so the absolute
 *  instant is stored; this only controls the wall-clock the user sees + edits. */
function toLocalInputValue(d: Date | undefined | null): string {
  if (!d) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const schema = z.object({
  name: z.string().min(1).optional(),
  description: z.string().nullable().optional(),
  enabled: z.boolean(),
  interval_value: z.number().min(1),
  interval_unit: z.enum(['seconds', 'minutes', 'hours', 'days']),
  timezone: z.string().optional(),
  start_at: z.date().nullable().optional(),
  send_in_app: z.boolean().optional(),
  send_email: z.boolean().optional(),
});

export type FormValues = z.infer<typeof schema>;

interface ScheduledTaskFormProps {
  task: ScheduledTask;
  onSubmit: (values: FormValues) => void;
  isSubmitting?: boolean;
}

export function ScheduledTaskForm({ task, onSubmit, isSubmitting }: ScheduledTaskFormProps) {
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: task.name,
      description: task.description ?? '',
      enabled: task.enabled,
      interval_value: task.interval_value,
      interval_unit: task.interval_unit as 'seconds' | 'minutes' | 'hours' | 'days',
      timezone: task.timezone || 'UTC',
      start_at: task.start_at ? parseDateTimeAsUTC(task.start_at) ?? undefined : undefined,
      send_in_app:
        task.key === 'user_sla_daily_summary'
          ? (task.metadata?.send_in_app as boolean | undefined) !== false
          : true,
      send_email:
        task.key === 'user_sla_daily_summary'
          ? (task.metadata?.send_email as boolean | undefined) !== false
          : true,
    },
  });

  const enabled = watch('enabled');
  const intervalUnit = watch('interval_unit');
  const startAt = watch('start_at');

  useEffect(() => {
    setValue('name', task.name);
    setValue('description', task.description ?? '');
    setValue('enabled', task.enabled);
    setValue('interval_value', task.interval_value);
    setValue('interval_unit', task.interval_unit as 'seconds' | 'minutes' | 'hours' | 'days');
    setValue('timezone', task.timezone || 'UTC');
    setValue(
      'start_at',
      task.start_at ? parseDateTimeAsUTC(task.start_at) ?? undefined : undefined,
    );
    if (task.key === 'user_sla_daily_summary') {
      setValue(
        'send_in_app',
        (task.metadata?.send_in_app as boolean | undefined) !== false,
      );
      setValue(
        'send_email',
        (task.metadata?.send_email as boolean | undefined) !== false,
      );
    }
  }, [task, setValue]);

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input id="name" {...register('name')} />
          {errors.name && (
            <p className="text-sm text-destructive">{errors.name.message}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="description">Description</Label>
          <Input id="description" {...register('description')} placeholder="Optional" />
        </div>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="enabled"
          checked={enabled}
          onCheckedChange={(v) => setValue('enabled', v, { shouldDirty: true })}
        />
        <Label htmlFor="enabled">Enabled</Label>
      </div>

      {task.key === 'user_sla_daily_summary' && (
        <div className="space-y-3 rounded-md border p-4">
          <p className="text-sm font-medium">Notification channels</p>
          <div className="flex items-center space-x-2">
            <Switch
              id="send_in_app"
              checked={watch('send_in_app') !== false}
              onCheckedChange={(v) =>
                setValue('send_in_app', v, { shouldDirty: true })}
            />
            <Label htmlFor="send_in_app">In-app</Label>
          </div>
          <div className="flex items-center space-x-2">
            <Switch
              id="send_email"
              checked={watch('send_email') !== false}
              onCheckedChange={(v) =>
                setValue('send_email', v, { shouldDirty: true })}
            />
            <Label htmlFor="send_email">Email</Label>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="space-y-2">
          <Label htmlFor="interval_value">Interval value</Label>
          <Input
            id="interval_value"
            type="number"
            min={1}
            {...register('interval_value', { valueAsNumber: true })}
          />
          {errors.interval_value && (
            <p className="text-sm text-destructive">{errors.interval_value.message}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="interval_unit">Interval unit</Label>
          <Select
            value={intervalUnit}
            onValueChange={(v) => setValue('interval_unit', v as 'seconds' | 'minutes' | 'hours' | 'days', { shouldDirty: true })}
          >
            <SelectTrigger id="interval_unit">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="seconds">Seconds</SelectItem>
              <SelectItem value="minutes">Minutes</SelectItem>
              <SelectItem value="hours">Hours</SelectItem>
              <SelectItem value="days">Days</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="timezone">Timezone</Label>
          <Input id="timezone" {...register('timezone')} placeholder="UTC" />
        </div>
      </div>

      <div className="space-y-2">
        <Label>Start date &amp; time (optional)</Label>
        <Input
          type="datetime-local"
          value={toLocalInputValue(startAt ?? undefined)}
          onChange={(e) =>
            setValue('start_at', e.target.value ? new Date(e.target.value) : null, {
              shouldDirty: true,
            })
          }
        />
        <p className="text-xs text-muted-foreground">
          In your local timezone. Anchors the first run; the task then repeats every interval.
          For a fixed daily time (e.g. 8:00 am), set the interval to 1 day.
        </p>
      </div>

      <Button type="submit" disabled={!isDirty || isSubmitting}>
        {isSubmitting ? 'Saving...' : 'Save changes'}
      </Button>
    </form>
  );
}

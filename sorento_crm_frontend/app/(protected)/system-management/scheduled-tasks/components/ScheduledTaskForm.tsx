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
import { DatePicker } from '@/components/ui/date-picker';
import type { ScheduledTask } from '../types/scheduledTask.types';
import { parseDateSafe } from '@/lib/helpers';

const schema = z.object({
  name: z.string().min(1).optional(),
  description: z.string().nullable().optional(),
  enabled: z.boolean(),
  interval_value: z.number().min(1),
  interval_unit: z.enum(['seconds', 'minutes', 'hours', 'days']),
  timezone: z.string().optional(),
  start_at: z.date().nullable().optional(),
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
      start_at: task.start_at ? parseDateSafe(task.start_at) ?? undefined : undefined,
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
      task.start_at ? parseDateSafe(task.start_at) ?? undefined : undefined,
    );
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
        <Label>Start date (optional)</Label>
        <DatePicker
          value={startAt ?? undefined}
          onChange={(d) => setValue('start_at', d ?? null, { shouldDirty: true })}
          placeholder="Optional start date"
        />
      </div>

      <Button type="submit" disabled={!isDirty || isSubmitting}>
        {isSubmitting ? 'Saving...' : 'Save changes'}
      </Button>
    </form>
  );
}

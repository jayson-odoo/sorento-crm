'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { useUpdateWorkCalendarConfig, useWorkCalendarConfig } from '../hooks/useWorkCalendar';
import { apiTimeToInputValue, inputValueToApiTime } from '../utils/timeFormat';

type WeekdayState = {
  monday: boolean;
  tuesday: boolean;
  wednesday: boolean;
  thursday: boolean;
  friday: boolean;
  saturday: boolean;
  sunday: boolean;
};

const defaultState: WeekdayState = {
  monday: true,
  tuesday: true,
  wednesday: true,
  thursday: true,
  friday: true,
  saturday: false,
  sunday: false,
};

export default function WorkCalendarConfigCard() {
  const { data, isLoading } = useWorkCalendarConfig();
  const updateMutation = useUpdateWorkCalendarConfig();
  const [state, setState] = useState<WeekdayState>(defaultState);
  const [startTime, setStartTime] = useState('09:00');
  const [endTime, setEndTime] = useState('17:00');

  useEffect(() => {
    if (data) {
      setState({
        monday: data.monday,
        tuesday: data.tuesday,
        wednesday: data.wednesday,
        thursday: data.thursday,
        friday: data.friday,
        saturday: data.saturday,
        sunday: data.sunday,
      });
      setStartTime(apiTimeToInputValue(data.work_day_start_time, '09:00'));
      setEndTime(apiTimeToInputValue(data.work_day_end_time, '17:00'));
    }
  }, [data]);

  const toggle = (key: keyof WeekdayState) => (value: boolean) => {
    setState((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = () => {
    updateMutation.mutate({
      ...state,
      work_day_start_time: inputValueToApiTime(startTime),
      work_day_end_time: inputValueToApiTime(endTime),
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Working Days</CardTitle>
        <CardDescription>
          Choose which weekdays count as working days. Delivery and business-day calculations use this together
          with public holidays.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-6 w-24" />
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {(
              [
                ['monday', 'Monday'],
                ['tuesday', 'Tuesday'],
                ['wednesday', 'Wednesday'],
                ['thursday', 'Thursday'],
                ['friday', 'Friday'],
                ['saturday', 'Saturday'],
                ['sunday', 'Sunday'],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={state[key]}
                  onCheckedChange={(value) => toggle(key)(Boolean(value))}
                />
                {label}
              </label>
            ))}
          </div>
        )}

        <div className="space-y-3 rounded-lg border bg-muted/30 p-4">
          <div>
            <p className="text-sm font-medium">Working hours (each working day)</p>
            <p className="text-sm text-muted-foreground">
              Standard start and end time for a business day. Used for configuration and future scheduling; business-day
              offsets still count full working days unless times are applied by a specific feature.
            </p>
          </div>
          {isLoading ? (
            <div className="flex flex-wrap gap-6">
              <Skeleton className="h-10 w-40" />
              <Skeleton className="h-10 w-40" />
            </div>
          ) : (
            <div className="flex flex-wrap items-end gap-6">
              <div className="space-y-2">
                <Label htmlFor="work-day-start">Day starts</Label>
                <Input
                  id="work-day-start"
                  type="time"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  className="w-[9rem] bg-background"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="work-day-end">Day ends</Label>
                <Input
                  id="work-day-end"
                  type="time"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  className="w-[9rem] bg-background"
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

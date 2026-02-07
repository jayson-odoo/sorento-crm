import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { useUpdateWorkCalendarConfig, useWorkCalendarConfig } from '../hooks/useWorkCalendar';

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
    }
  }, [data]);

  const toggle = (key: keyof WeekdayState) => (value: boolean) => {
    setState((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = () => {
    updateMutation.mutate(state);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Working Days</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
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

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

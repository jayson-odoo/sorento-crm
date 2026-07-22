'use client';

import { useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Switch } from '@/components/ui/switch';

function DemoSelect({
  defaultValue,
  placeholder = 'Select',
  options,
  triggerClassName = 'w-full',
}: {
  defaultValue: string;
  placeholder?: string;
  options: { value: string; label: string }[];
  triggerClassName?: string;
}) {
  const [value, setValue] = useState(defaultValue);
  return (
    <SearchableSelect
      value={value}
      onChange={setValue}
      options={options}
      placeholder={placeholder}
      triggerClassName={triggerClassName}
    />
  );
}

const AdvancedSettingsPreferences = () => {
  const id1 = useId();
  const id2 = useId();

  return (
    <Card>
      <CardHeader id="advanced_settings_preferences">
        <CardTitle>Preferences</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-5 lg:py-7.5">
        <div className="flex items-baseline flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-56">Language</Label>
          <div className="grow">
            <DemoSelect
              defaultValue="1"
              placeholder="Select"
              triggerClassName="w-full"
              options={[
                { value: '1', label: 'American English' },
                { value: '2', label: 'Option 2' },
                { value: '3', label: 'Option 3' },
              ]}
            />
          </div>
        </div>
        <div className="flex items-baseline flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-56">Time zone</Label>
          <div className="grow">
            <DemoSelect
              defaultValue="4"
              placeholder="Select"
              triggerClassName="w-full"
              options={[
                { value: '4', label: 'GMT -5:00 - Eastern Time(US & Canada)' },
                { value: '5', label: 'Option 2' },
                { value: '6', label: 'Option 3' },
              ]}
            />
          </div>
        </div>
        <div className="flex items-baseline flex-wrap lg:flex-nowrap gap-2.5 mb-2">
          <Label className="flex w-full max-w-56">Currency</Label>
          <div className="grow">
            <DemoSelect
              defaultValue="7"
              placeholder="Select"
              triggerClassName="w-full"
              options={[
                { value: '7', label: 'United States Dollar (USD)' },
                { value: '8', label: 'Option 2' },
                { value: '9', label: 'Option 3' },
              ]}
            />
          </div>
        </div>
        <div className="flex items-center flex-wrap lg:flex-nowrap gap-2.5">
          <Label className="flex w-full max-w-56">Open tasks as...</Label>
          <div className="flex items-center gap-5">
            <RadioGroup
              defaultValue="intermediate"
              className="flex items-center gap-5"
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="intermediate" id={id1} />
                <Label
                  htmlFor={id1}
                  className="text-foreground text-sm font-normal"
                >
                  Modal
                </Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="beginner" id={id2} />
                <Label
                  htmlFor={id2}
                  className="text-foreground text-sm font-normal"
                >
                  Fullscreen
                </Label>
              </div>
            </RadioGroup>
          </div>
        </div>
        <div className="flex flex-wrap gap-2.5 mb-1.5">
          <Label className="flex w-full max-w-56">Attributes</Label>
          <div className="flex flex-col items-start gap-5">
            <div className="flex flex-col gap-2.5">
              <div className="flex items-center space-x-2">
                <Checkbox />
                <Label>Show list names</Label>
              </div>
              <div className="form-hint">See the name next to each icon</div>
            </div>
            <div className="flex flex-col gap-2.5">
              <div className="flex items-center space-x-2">
                <Checkbox defaultChecked />
                <Label>Show linked task names</Label>
              </div>
              <div className="form-hint">
                Show task names next to ids for linked project tasks.
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center flex-wrap gap-2.5">
          <Label className="flex w-full max-w-56">Email visibility</Label>
          <Switch defaultChecked size="sm" />
          <Label htmlFor="auto-update" className="text-foreground text-sm">
            Visible
          </Label>
        </div>
        <div className="flex justify-end">
          <Button>Save Changes</Button>
        </div>
      </CardContent>
    </Card>
  );
};

export { AdvancedSettingsPreferences };

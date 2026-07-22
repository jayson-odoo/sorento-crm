'use client';

import { ReactNode, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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

interface IBackupSettingsItem {
  title: string;
  description: string;
  control: ReactNode;
}
type IBackupSettingsItems = Array<IBackupSettingsItem>;

const BackupSettings = () => {
  const items: IBackupSettingsItems = [
    {
      title: 'Automatic Backup',
      description: 'Scheduled Data Protection',
      control: <Switch id="size-sm" size="sm" defaultChecked />,
    },
    {
      title: 'Backup Frequency',
      description: 'Select Preferred Backup',
      control: (
        <DemoSelect
          defaultValue="1"
          placeholder="Select"
          triggerClassName="w-24"
          options={[
            { value: '1', label: 'Daily' },
            { value: '2', label: 'Weekly' },
            { value: '3', label: 'Monthly' },
            { value: '4', label: 'Yearly' },
          ]}
        />
      ),
    },
    {
      title: 'Manual Backup',
      description: 'Backup When Needed',
      control: <Button variant="outline">Start</Button>,
    },
  ];

  const renderItem = (item: IBackupSettingsItem, index: number) => {
    return (
      <CardContent
        key={index}
        className="border-b border-border flex items-center justify-between py-4 gap-2.5"
      >
        <div className="flex flex-col justify-center gap-1.5">
          <span className="leading-none font-medium text-sm text-mono">
            {item.title}
          </span>
          <span className="text-sm text-secondary-foreground">
            {item.description}
          </span>
        </div>
        {item.control}
      </CardContent>
    );
  };

  return (
    <Card>
      <CardHeader className="mb-1">
        <CardTitle>Backup Settings</CardTitle>
      </CardHeader>
      {items.map((item, index) => {
        return renderItem(item, index);
      })}
    </Card>
  );
};

export { BackupSettings, type IBackupSettingsItem, type IBackupSettingsItems };

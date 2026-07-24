'use client';

import { ReactNode, useState } from 'react';
import { CardNotification } from '@/partials/cards';
import {
  ArrowRight,
  ArrowRightCircle,
  EyeOff,
  LucideIcon,
  Monitor,
} from 'lucide-react';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
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

interface AccessibilityItem {
  icon: LucideIcon;
  title: string;
  description: string;
  actions: ReactNode;
}
type AccessibilityItems = Array<AccessibilityItem>;

const Accessibility = () => {
  const items: AccessibilityItems = [
    {
      icon: ArrowRightCircle,
      title: 'Shortcuts require modifier',
      description: 'Enable modifier keys for quick keyboard shortcuts.',
      actions: <Switch id="size-sm" size="sm" defaultChecked />,
    },
    {
      icon: EyeOff,
      title: 'High color contrast',
      description: 'Improve readability with high-contrast interface colors.',
      actions: <Switch id="size-sm" size="sm" />,
    },
    {
      icon: ArrowRight,
      title: 'Autoplay videos',
      description: 'Choose preferences for automatic video playback.',
      actions: (
        <div className="grow min-w-48">
          <DemoSelect
            defaultValue="1"
            placeholder="Select"
            triggerClassName="w-full"
            options={[
              { value: '1', label: 'System preferences' },
              { value: '2', label: 'Sound' },
              { value: '3', label: 'Focus' },
            ]}
          />
        </div>
      ),
    },
    {
      icon: Monitor,
      title: 'Open links in Desktop',
      description: 'Links open in the desktop app for convenience.',
      actions: <Switch id="size-sm" size="sm" defaultChecked />,
    },
  ];

  const renderItem = (item: AccessibilityItem, index: number) => {
    return (
      <CardNotification
        icon={item.icon}
        title={item.title}
        description={item.description}
        actions={item.actions}
        key={index}
      />
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Accessibility</CardTitle>
      </CardHeader>
      <div id="notifications_cards">
        {items.map((item, index) => {
          return renderItem(item, index);
        })}
      </div>
    </Card>
  );
};

export { Accessibility, type AccessibilityItems };

'use client';

import { useState } from 'react';
import { getTimeZones } from '@/i18n/timezones';
import { SearchableSelect } from '@/components/common/SearchableSelect';

const TimezoneSelect = ({
  defaultValue = '',
  onChange,
}: {
  defaultValue: string | undefined;
  onChange: (value: string) => void;
}) => {
  const [value, setValue] = useState<string>(defaultValue);
  const timeZoneList = getTimeZones();

  return (
    <SearchableSelect
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
      placeholder="Select a timezone"
      emptyMessage="No timezone found."
      triggerClassName="w-full"
      options={timeZoneList.map(({ value: itemValue, label }) => ({
        value: itemValue,
        label,
        // The old picker matched on the IANA id ("Asia/Kuala_Lumpur"), not the label,
        // so keep both searchable — neither spelling should stop working.
        searchText: `${itemValue} ${label}`,
      }))}
    />
  );
};

export default TimezoneSelect;

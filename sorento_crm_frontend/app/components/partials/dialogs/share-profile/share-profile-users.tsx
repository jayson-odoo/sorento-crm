'use client';

import { useState } from 'react';
import Link from 'next/link';
import { toAbsoluteUrl } from '@/lib/helpers';
import { SearchableSelect } from '@/components/common/SearchableSelect';

function RoleSelect({ defaultRole }: { defaultRole: string }) {
  const [role, setRole] = useState(defaultRole);
  return (
    <SearchableSelect
      value={role}
      onChange={setRole}
      options={[
        { value: 'owner', label: 'Owner' },
        { value: 'editor', label: 'Editor' },
        { value: 'viewer', label: 'Viewer' },
      ]}
      placeholder="Role"
      size="sm"
      triggerClassName="w-24"
    />
  );
}

export function ShareProfileUsers() {
  const items = [
    {
      avatar: '300-3.png',
      userName: 'Tyler Hero',
      email: 'tyler.hero@gmail.com',
      role: 'owner',
    },
    {
      avatar: '300-1.png',
      userName: 'Esther Howard',
      email: 'esther.howard@gmail.com',
      role: 'editor',
    },
    {
      avatar: '300-11.png',
      userName: 'Jacob Jones',
      email: 'jacob.jones@gmail.com',
      role: 'viewer',
    },
  ];

  return (
    <div className="flex flex-col px-5 gap-2.5">
      {items.map((item, index) => (
        <div key={index} className="flex items-center flex-wrap gap-2">
          <div className="flex items-center grow gap-2.5">
            <img
              src={toAbsoluteUrl(`/media/avatars/${item.avatar}`)}
              className="rounded-full size-9 shrink-0"
              alt={`${item.userName} avatar`}
            />
            <div className="flex flex-col">
              <Link
                href="#"
                className="text-sm font-semibold text-mono hover:text-primary-active mb-px"
              >
                {item.userName}
              </Link>
              <Link
                href="#"
                className="hover:text-primary-active text-sm font-medium text-secondary-foreground"
              >
                {item.email}
              </Link>
            </div>
          </div>

          <RoleSelect defaultRole={item.role} />
        </div>
      ))}
    </div>
  );
}

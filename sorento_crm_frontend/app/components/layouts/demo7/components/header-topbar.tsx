'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { UserDropdownMenu } from '@/partials/topbar/user-dropdown-menu';
import { SessionUserAvatar } from '@/partials/topbar/session-user-avatar';
import { ArrowUp, Crown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { StoreClientTopbar } from '@/app/(protected)/store-client/components/common/topbar';

const HeaderTopbar = () => {
  const pathname = usePathname();

  return (
    <div className="flex items-center flex-wrap gap-2 lg:gap-3.5">
      {pathname.startsWith('/store-client') ? (
        <StoreClientTopbar />
      ) : (
        <>
          <div className="flex items-center gap-2.5 lg:gap-3.5">
            <div className="flex flex-col items-end pt-0.5">
              <span className="inline-flex gap-0.5 text-foreground font-medium text-xs uppercase">
                <Crown className="size-3.5" />
                free
              </span>
              <span className="text-secondary-foreground text-xs">
                182/200 <span className="hidden sm:inline-block">Uploads</span>
              </span>
            </div>

            <Button size="sm" asChild>
              <Link href="/account/security/privacy-settings">
                Upgrade
                <ArrowUp />
              </Link>
            </Button>
          </div>

          <div className="border-e border-border h-5 mx-1.5 lg:mx-3"></div>

          <UserDropdownMenu
            trigger={
              <SessionUserAvatar className="cursor-pointer size-[34px] rounded-full border border-input object-cover shrink-0" />
            }
          />
        </>
      )}
    </div>
  );
};

export { HeaderTopbar };

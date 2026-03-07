'use client';

import { useState } from 'react';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { Badge, BadgeDot, BadgeProps } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { User, UserStatus } from '@/app/models/user';
import { getUserStatusProps } from '../../constants/status';
import UserProfileEditDialog from './user-profile-edit-dialog';

const UserProfile = ({
  user,
  isLoading,
}: {
  user: User;
  isLoading: boolean;
}) => {
  const [isEditDialogOpen, setEditDialogOpen] = useState(false);

  const Loading = () => (
    <Card>
      <CardContent>
        <dl className="grid grid-cols-[auto_1fr] text-muted-foreground gap-3 text-sm mb-5">
          <div className="grid grid-cols-subgrid col-span-2 items-baseline">
            <dt className="flex md:w-64">
              <Skeleton className="h-6 w-24" />
            </dt>
            <dd>
              <Skeleton className="h-5 w-36" />
            </dd>
          </div>
          <div className="grid grid-cols-subgrid col-span-2 items-baseline">
            <dt>
              <Skeleton className="h-5 w-36" />
            </dt>
            <dd>
              <Skeleton className="h-5 w-48" />
            </dd>
          </div>
          <div className="grid grid-cols-subgrid col-span-2 items-baseline">
            <dt>
              <Skeleton className="h-5 w-20" />
            </dt>
            <dd>
              <Skeleton className="h-5 w-24" />
            </dd>
          </div>
          <div className="grid grid-cols-subgrid col-span-2 items-baseline">
            <dt>
              <Skeleton className="h-5 w-24" />
            </dt>
            <dd>
              <Skeleton className="h-5 w-20" />
            </dd>
          </div>
          <div className="grid grid-cols-subgrid col-span-2 items-baseline">
            <dt>
              <Skeleton className="h-5 w-36" />
            </dt>
            <dd>
              <Skeleton className="h-5 w-24" />
            </dd>
          </div>
          <div className="grid grid-cols-subgrid col-span-2 items-baseline">
            <dt>
              <Skeleton className="h-5 w-24" />
            </dt>
            <dd>
              <Skeleton className="h-5 w-36" />
            </dd>
          </div>
          <div className="grid grid-cols-subgrid col-span-2 items-baseline">
            <dt>
              <Skeleton className="h-5 w-32" />
            </dt>
            <dd>
              <Skeleton className="h-5 w-24" />
            </dd>
          </div>
          <div className="grid grid-cols-subgrid col-span-2 items-baseline">
            <dt>
              <Skeleton className="h-5 w-36" />
            </dt>
            <dd>
              <Skeleton className="h-5 w-20" />
            </dd>
          </div>
          <div className="grid grid-cols-subgrid col-span-2 items-baseline">
            <dt>
              <Skeleton className="h-5 w-32" />
            </dt>
            <dd>
              <Skeleton className="h-5 w-24" />
            </dd>
          </div>
          <div className="grid grid-cols-subgrid col-span-2 items-baseline">
            <dt>
              <Skeleton className="h-5 w-36" />
            </dt>
            <dd>
              <Skeleton className="h-5 w-20" />
            </dd>
          </div>
        </dl>
        <Skeleton className="h-9 w-32" />
      </CardContent>
    </Card>
  );

  const Content = () => {
    const statusPros = getUserStatusProps(user.status as UserStatus);
    const statusVariant = statusPros.variant as keyof BadgeProps['variant'];

    return (
      <Card>
        <CardContent>
          <dl className="grid grid-cols-[auto_1fr] gap-3 text-sm mb-5 [&_dt]:text-muted-foreground">
            <div className="grid grid-cols-subgrid col-span-2 items-baseline">
              <dt className="flex md:w-64">Full name:</dt>
              <dd>{user.name || 'Not available'}</dd>
            </div>
            <div className="grid grid-cols-subgrid col-span-2 items-baseline">
              <dt>Email address:</dt>
              <dd className="flex items-center gap-2.5">
                <span>{user.email}</span>
                {user.emailVerifiedAt ? (
                  <Badge variant="secondary" appearance="light">
                    Verified
                  </Badge>
                ) : (
                  <Badge variant="warning" appearance="light">
                    Not verified
                  </Badge>
                )}
              </dd>
            </div>
            <div className="grid grid-cols-subgrid col-span-2 items-baseline">
              <dt>Roles:</dt>
              <dd>
                <span className="inline-flex flex-wrap items-center gap-1.5">
                  {user.roles?.length
                    ? user.roles.map((r) => (
                        <Badge key={r.id} variant="secondary" appearance="light">
                          {r.name}
                        </Badge>
                      ))
                    : <span className="text-muted-foreground">No roles assigned</span>}
                </span>
              </dd>
            </div>
            <div className="grid grid-cols-subgrid col-span-2 items-baseline">
              <dt>Status:</dt>
              <dd>
                <div className="inline-flex gap-2.5">
                  <Badge variant={statusVariant} appearance="ghost">
                    <BadgeDot />
                    {statusPros.label}
                  </Badge>
                  {user.isTrashed && (
                    <Badge variant="destructive" appearance="light">
                      Trashed
                    </Badge>
                  )}
                </div>
              </dd>
            </div>
            <div className="grid grid-cols-subgrid col-span-2 items-baseline">
              <dt>Last Sign In:</dt>
              <dd>
                {user.lastSignInAt ? formatDateTimeInMalaysia(user.lastSignInAt) : 'Never'}
              </dd>
            </div>
            <div className="grid grid-cols-subgrid col-span-2 items-baseline">
              <dt>Respond User ID:</dt>
              <dd>
                {user.respondUserId ? (
                  <span className="font-mono">{user.respondUserId}</span>
                ) : (
                  <span className="text-muted-foreground">Not set</span>
                )}
              </dd>
            </div>
            <div className="grid grid-cols-subgrid col-span-2 items-baseline">
              <dt>Respond Sync Status:</dt>
              <dd>
                {user.respondSynced ? (
                  <Badge
                    variant={
                      user.respondSynced === 'successful'
                        ? 'success'
                        : user.respondSynced === 'failed'
                          ? 'destructive'
                          : user.respondSynced === 'pending'
                            ? 'warning'
                            : 'secondary'
                    }
                    appearance="light"
                  >
                    {user.respondSynced.charAt(0).toUpperCase() + user.respondSynced.slice(1)}
                  </Badge>
                ) : (
                  <span className="text-muted-foreground">Not synced</span>
                )}
              </dd>
            </div>
            {user.superiorId && (
              <div className="grid grid-cols-subgrid col-span-2 items-baseline">
                <dt>Superior:</dt>
                <dd>
                  <span>
                    {user.superiorName || user.superiorId}
                  </span>
                </dd>
              </div>
            )}
          </dl>
          <Button
            variant="outline"
            onClick={() => setEditDialogOpen(true)}
          >
            Edit user details
          </Button>
        </CardContent>
      </Card>
    );
  };

  return (
    <>
      {isLoading || !user ? <Loading /> : <Content />}

      <UserProfileEditDialog
        open={isEditDialogOpen}
        closeDialog={() => setEditDialogOpen(false)}
        user={user}
      />
    </>
  );
};

export default UserProfile;

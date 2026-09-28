'use client';

import { useUser } from './components/user-context';
import UserDangerZone from './components/user-danger-zone';
import UserProfile from './components/user-profile';
import UserSignInSection from './components/user-sign-in-section';

export default function Page() {
  const { user, isLoading } = useUser();

  return (
    <div className="space-y-10">
      <UserProfile user={user} isLoading={isLoading} />
      {!isLoading && user && <UserSignInSection user={user} />}
      <UserDangerZone user={user} isLoading={isLoading} />
    </div>
  );
}

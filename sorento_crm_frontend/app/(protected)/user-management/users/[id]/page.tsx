'use client';

import { useUser } from './components/user-context';
import UserDangerZone from './components/user-danger-zone';
import UserProfile from './components/user-profile';
import UserAccessAgents from './components/UserAccessAgents';

export default function Page() {
  const { user, isLoading } = useUser();

  return (
    <div className="space-y-10">
      <UserProfile user={user} isLoading={isLoading} />
      {user && <UserAccessAgents userId={user.id} />}
      <UserDangerZone user={user} isLoading={isLoading} />
    </div>
  );
}

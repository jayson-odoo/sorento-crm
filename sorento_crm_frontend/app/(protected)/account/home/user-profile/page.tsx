import { redirect } from 'next/navigation';

/**
 * Legacy Metronic demo URL. Real profile (name + photo) is under User Management → Account.
 */
export default function AccountUserProfilePage() {
  redirect('/user-management/account');
}

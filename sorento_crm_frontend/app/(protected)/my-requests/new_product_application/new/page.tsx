'use client';

import NewProductApplicationForm from '@/app/(auth)/portal/components/NewProductApplicationForm';
import { MySlug } from '../../MySlug';

export default function MyRequestsNewProductApplicationNewPage() {
  return <MySlug>{(slug) => <NewProductApplicationForm slug={slug} />}</MySlug>;
}

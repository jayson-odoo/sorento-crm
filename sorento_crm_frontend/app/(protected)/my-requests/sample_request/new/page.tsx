'use client';

import SampleRequestForm from '@/app/(auth)/portal/components/SampleRequestForm';
import { MySlug } from '../../MySlug';

export default function MyRequestsSampleRequestNewPage() {
  return <MySlug>{(slug) => <SampleRequestForm slug={slug} />}</MySlug>;
}

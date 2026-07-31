'use client';

import { useComplaintRootCause } from '../hooks/useComplaintRootCauses';
import { MasterDataComplaintsDetail } from '../../_shared/MasterDataComplaintsDetail';

export default function ComplaintRootCauseDetail({ id }: { id: string }) {
  const { data, isLoading } = useComplaintRootCause(id);
  return (
    <MasterDataComplaintsDetail
      kind="root_cause"
      id={id}
      record={data ?? undefined}
      isLoading={isLoading}
      listHref="/complaint-management/complaint-root-causes"
      listLabel="root causes"
    />
  );
}

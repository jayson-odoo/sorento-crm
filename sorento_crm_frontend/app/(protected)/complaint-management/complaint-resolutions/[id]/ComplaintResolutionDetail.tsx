'use client';

import { useComplaintResolution } from '../hooks/useComplaintResolutions';
import { MasterDataComplaintsDetail } from '../../_shared/MasterDataComplaintsDetail';

export default function ComplaintResolutionDetail({ id }: { id: string }) {
  const { data, isLoading } = useComplaintResolution(id);
  return (
    <MasterDataComplaintsDetail
      kind="resolution"
      id={id}
      record={data ?? undefined}
      isLoading={isLoading}
      listHref="/complaint-management/complaint-resolutions"
      listLabel="resolutions"
    />
  );
}

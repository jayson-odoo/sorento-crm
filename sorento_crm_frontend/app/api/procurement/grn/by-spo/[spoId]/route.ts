import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma picking header to frontend expected format (snake_case)
 */
function transformGRN(grn: any) {
  return {
    id: grn.id,
    picking_number: grn.pickingNumber,
    picking_type: grn.pickingType,
    source_entity_type: grn.sourceEntityType,
    source_entity_id: grn.sourceEntityId,
    picking_date: grn.pickingDate,
    picked_by_user_id: grn.pickedByUserId,
    inspection_status: grn.inspectionStatus,
    quality_remarks: grn.qualityRemarks,
    inspected_by_user_id: grn.inspectedByUserId,
    inspection_date: grn.inspectionDate,
    picking_status: grn.pickingStatus,
    total_items_picked: grn.totalItemsPicked,
    total_items_discrepancy: grn.totalItemsDiscrepancy,
    total_cost: grn.totalCost ? Number(grn.totalCost) : null,
    notes: grn.notes,
    created_at: grn.createdAt,
    updated_at: grn.updatedAt,
  };
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ spoId: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { spoId } = await params;

    // Find all GRN lines that reference this SPO allocation
    const pickingLines = await prisma.pickingLine.findMany({
      where: {
        spoAllocationId: spoId,
      },
      include: {
        pickingHeader: true,
      },
      orderBy: {
        createdAt: 'asc',
      },
    });

    // Get unique GRN headers
    const grnIds = Array.from(new Set(pickingLines.map((line: { pickingHeaderId: string }) => line.pickingHeaderId)));

    const grns = await prisma.pickingHeader.findMany({
      where: {
        id: { in: grnIds },
        pickingType: 'goods_received',
      },
      include: {
        _count: {
          select: {
            pickingLines: true,
          },
        },
      },
      orderBy: {
        createdAt: 'asc',
      },
    });

    // Transform to snake_case for frontend
    const transformedGRNs = grns.map((grn) => ({
      ...transformGRN(grn),
      lines_count: grn._count?.pickingLines || 0,
    }));

    return NextResponse.json({
      data: transformedGRNs,
      pagination: {
        total: grns.length,
        page: 1,
        limit: grns.length,
      },
      empty: grns.length === 0,
    });
  } catch (error) {
    console.error('Error fetching GRN by SPO:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

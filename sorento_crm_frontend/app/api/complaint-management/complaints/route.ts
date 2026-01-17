import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import type { Prisma } from '@prisma/client';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma complaint to frontend expected format (snake_case)
 */
function transformComplaint(complaint: any) {
  return {
    id: complaint.id,
    delivery_order_number: complaint.deliveryOrderNumber,
    complaint_date: complaint.complaintDate,
    customer_type: complaint.customerType,
    customer_type_others: complaint.customerTypeOthers,
    within_warranty: complaint.withinWarranty,
    product_type: complaint.productType,
    defects_discovered: complaint.defectsDiscovered,
    complaint_type: complaint.complaintType,
    defect_description: complaint.defectDescription,
    product_code: complaint.productCode,
    salesperson: complaint.salesperson,
    customer_name: complaint.customerName,
    contact_person: complaint.contactPerson,
    contact_number: complaint.contactNumber,
    customer_address: complaint.customerAddress,
    project_title: complaint.projectTitle,
    attachments: complaint.attachments
      ? complaint.attachments.map((att: any) => ({
          id: att.id,
          complaint_id: att.complaintId,
          file_name: att.fileName,
          file_url: att.fileUrl,
          file_size_bytes: att.fileSizeBytes,
          uploaded_at: att.uploadedAt,
        }))
      : [],
  };
}

export async function GET(req: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { searchParams } = new URL(req.url);
    const page = parseInt(searchParams.get('page') || '1', 10);
    const limit = parseInt(searchParams.get('limit') || '50', 10);
    const query = searchParams.get('query') || '';
    const sortField = searchParams.get('sort') || 'complaint_date';
    const sortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';

    // Build where clause with filters
    const whereClause: any = {
      ...(query
        ? {
            OR: [
              { deliveryOrderNumber: { contains: query, mode: 'insensitive' } },
              { customerName: { contains: query, mode: 'insensitive' } },
              { productCode: { contains: query, mode: 'insensitive' } },
              { defectDescription: { contains: query, mode: 'insensitive' } },
              { projectTitle: { contains: query, mode: 'insensitive' } },
            ],
          }
        : {}),
    };

    const totalCount = await prisma.complaint.count({ where: whereClause });

    // Map sort field
    const sortMap: Record<string, string> = {
      complaint_date: 'complaintDate',
      delivery_order_number: 'deliveryOrderNumber',
      customer_name: 'customerName',
      product_code: 'productCode',
    };
    const mappedSortField = sortMap[sortField] || 'complaintDate';

    const complaints = await prisma.complaint.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      include: {
        attachments: {
          orderBy: { uploadedAt: 'desc' },
        },
      },
      orderBy: { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedComplaints = complaints.map(transformComplaint);

    return NextResponse.json({
      data: transformedComplaints,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching complaints:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const body = await request.json();

    const complaint = await prisma.$transaction(async (tx: Prisma.TransactionClient) => {
      const newComplaint = await tx.complaint.create({
        data: {
          deliveryOrderNumber: body.delivery_order_number || null,
          complaintDate: body.complaint_date
            ? new Date(body.complaint_date)
            : null,
          customerType: body.customer_type || null,
          customerTypeOthers: body.customer_type_others || null,
          withinWarranty: body.within_warranty || null,
          productType: body.product_type || null,
          defectsDiscovered: body.defects_discovered || null,
          complaintType: body.complaint_type || null,
          defectDescription: body.defect_description || null,
          productCode: body.product_code || null,
          salesperson: body.salesperson || null,
          customerName: body.customer_name || null,
          contactPerson: body.contact_person || null,
          contactNumber: body.contact_number || null,
          customerAddress: body.customer_address || null,
          projectTitle: body.project_title || null,
        },
        select: {
          id: true,
        },
      });

      // Create attachments if provided
      if (body.attachments && Array.isArray(body.attachments)) {
        await tx.complaintAttachment.createMany({
          data: body.attachments.map((att: any) => ({
            complaintId: newComplaint.id,
            fileName: att.file_name || null,
            fileUrl: att.file_url || null,
            fileSizeBytes: att.file_size_bytes || null,
          })),
        });
      }

      // Fetch the complete complaint with attachments
      const fullComplaint = await tx.complaint.findUnique({
        where: { id: newComplaint.id },
        include: {
          attachments: {
            orderBy: { uploadedAt: 'desc' },
          },
        },
      });

      if (!fullComplaint) {
        throw new Error('Failed to fetch created complaint');
      }

      return fullComplaint;
    });

    if (!complaint) {
      return NextResponse.json(
        { message: 'Failed to create complaint' },
        { status: 500 },
      );
    }

    // Transform to snake_case for frontend
    const transformedComplaint = transformComplaint(complaint);

    return NextResponse.json(transformedComplaint, { status: 201 });
  } catch (error) {
    console.error('Error creating complaint:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

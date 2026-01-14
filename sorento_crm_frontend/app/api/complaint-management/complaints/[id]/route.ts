import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
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

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Skip validation for special routes like "new"
    if (id === 'new' || id === 'edit') {
      return NextResponse.json(
        { message: 'Invalid complaint ID' },
        { status: 404 },
      );
    }

    // Validate UUID format
    const uuidRegex =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid complaint ID format' },
        { status: 400 },
      );
    }

    const complaint = await prisma.complaint.findUnique({
      where: { id },
      include: {
        attachments: {
          orderBy: { uploadedAt: 'desc' },
        },
      },
    });

    if (!complaint) {
      return NextResponse.json(
        { message: 'Complaint not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedComplaint = transformComplaint(complaint);

    return NextResponse.json(transformedComplaint);
  } catch (error) {
    console.error('Error fetching complaint:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;
    const body = await request.json();

    const complaint = await prisma.$transaction(async (tx) => {
      // Update complaint
      await tx.complaint.update({
        where: { id },
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
      });

      // Delete existing attachments if new ones are provided
      if (body.attachments && Array.isArray(body.attachments)) {
        await tx.complaintAttachment.deleteMany({
          where: { complaintId: id },
        });

        // Create new attachments
        if (body.attachments.length > 0) {
          await tx.complaintAttachment.createMany({
            data: body.attachments.map((att: any) => ({
              complaintId: id,
              fileName: att.file_name || null,
              fileUrl: att.file_url || null,
              fileSizeBytes: att.file_size_bytes || null,
            })),
          });
        }
      }

      // Fetch the complete complaint with attachments
      return await tx.complaint.findUnique({
        where: { id },
        include: {
          attachments: {
            orderBy: { uploadedAt: 'desc' },
          },
        },
      });
    });

    if (!complaint) {
      return NextResponse.json(
        { message: 'Complaint not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedComplaint = transformComplaint(complaint);

    return NextResponse.json(transformedComplaint);
  } catch (error) {
    console.error('Error updating complaint:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to update not found')
    ) {
      return NextResponse.json(
        { message: 'Complaint not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Delete complaint (cascade will delete attachments)
    await prisma.complaint.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'Complaint deleted successfully' });
  } catch (error) {
    console.error('Error deleting complaint:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to delete does not exist')
    ) {
      return NextResponse.json(
        { message: 'Complaint not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

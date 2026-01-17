import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

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

    const entityType = searchParams.get('entity_type');
    const entityId = searchParams.get('entity_id');

    const whereClause: any = {
      isDeleted: false,
      ...(entityType ? { entityType } : {}),
      ...(entityId ? { entityId } : {}),
    };

    const totalCount = await prisma.attachment.count({ where: whereClause });

    const attachments = await prisma.attachment.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      include: {
        attachmentType: true,
      },
      orderBy: {
        uploadedAt: 'desc',
      },
    });

    // Transform to snake_case for frontend
    const transformedAttachments = attachments.map((a: {
      id: string;
      attachmentTypeId: string | null;
      originalFilename: string;
      storedFilename: string;
      filePath: string;
      fileSizeBytes: number | null;
      mimeType: string | null;
      fileHash: string | null;
      entityType: string | null;
      entityId: string | null;
      uploadedBy: string | null;
      uploadedAt: Date;
      isDeleted: boolean;
      deletedAt: Date | null;
      deletedBy: string | null;
      attachmentType: { id: string; typeName: string; description: string | null } | null;
    }) => ({
      id: a.id,
      attachment_type_id: a.attachmentTypeId,
      original_filename: a.originalFilename,
      stored_filename: a.storedFilename,
      file_path: a.filePath,
      file_size_bytes: a.fileSizeBytes,
      mime_type: a.mimeType,
      file_hash: a.fileHash,
      entity_type: a.entityType,
      entity_id: a.entityId,
      uploaded_by: a.uploadedBy,
      uploaded_at: a.uploadedAt,
      is_deleted: a.isDeleted,
      deleted_at: a.deletedAt,
      deleted_by: a.deletedBy,
      attachment_type: a.attachmentType ? {
        id: a.attachmentType.id,
        type_name: a.attachmentType.typeName,
        description: a.attachmentType.description,
      } : undefined,
    }));

    return NextResponse.json({
      data: transformedAttachments,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching attachments:', error);
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

    const formData = await request.formData();
    const file = formData.get('file') as File;
    const entityType = formData.get('entity_type') as string;
    const entityId = formData.get('entity_id') as string;

    if (!file || !entityType || !entityId) {
      return NextResponse.json(
        { message: 'Missing required fields' },
        { status: 400 },
      );
    }

    // Note: File storage implementation needed (S3 or local filesystem)
    // For now, creating the database record with placeholder values
    const storedFilename = `${Date.now()}-${file.name}`;
    const filePath = `/uploads/${entityType}/${entityId}/${storedFilename}`;

    const attachment = await prisma.attachment.create({
      data: {
        originalFilename: file.name,
        storedFilename: storedFilename,
        filePath: filePath,
        fileSizeBytes: file.size || null,
        mimeType: file.type || null,
        entityType: entityType,
        entityId: entityId,
        uploadedBy: session.user?.id || null,
      },
      include: {
        attachmentType: true,
      },
    });

    // Transform to snake_case for frontend
    const transformedAttachment = {
      id: attachment.id,
      attachment_type_id: attachment.attachmentTypeId,
      original_filename: attachment.originalFilename,
      stored_filename: attachment.storedFilename,
      file_path: attachment.filePath,
      file_size_bytes: attachment.fileSizeBytes,
      mime_type: attachment.mimeType,
      file_hash: attachment.fileHash,
      entity_type: attachment.entityType,
      entity_id: attachment.entityId,
      uploaded_by: attachment.uploadedBy,
      uploaded_at: attachment.uploadedAt,
      is_deleted: attachment.isDeleted,
      deleted_at: attachment.deletedAt,
      deleted_by: attachment.deletedBy,
      attachment_type: attachment.attachmentType ? {
        id: attachment.attachmentType.id,
        type_name: attachment.attachmentType.typeName,
        description: attachment.attachmentType.description,
      } : undefined,
    };

    return NextResponse.json(transformedAttachment, { status: 201 });
  } catch (error) {
    console.error('Error uploading attachment:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

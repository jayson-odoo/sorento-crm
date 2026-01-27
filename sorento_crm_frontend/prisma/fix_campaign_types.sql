-- Fix campaign_types table: Add columns with defaults for existing rows
-- Run this SQL script directly on your database before running prisma db push

-- Step 1: Add type_code column with default, then update existing rows
ALTER TABLE campaign_types 
ADD COLUMN IF NOT EXISTS type_code VARCHAR(50) DEFAULT gen_random_uuid()::text;

-- Update existing rows to have unique type codes (using UUID)
UPDATE campaign_types 
SET type_code = gen_random_uuid()::text 
WHERE type_code IS NULL;

-- Step 2: Add updated_at column with default
ALTER TABLE campaign_types 
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP;

-- Update existing rows to have updated_at set to created_at or now
UPDATE campaign_types 
SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)
WHERE updated_at IS NULL;

-- Step 3: Make type_code NOT NULL and add unique constraint
ALTER TABLE campaign_types 
ALTER COLUMN type_code SET NOT NULL;

ALTER TABLE campaign_types 
ALTER COLUMN updated_at SET NOT NULL;

-- Add unique constraint if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'campaign_types_type_code_key'
    ) THEN
        ALTER TABLE campaign_types 
        ADD CONSTRAINT campaign_types_type_code_key UNIQUE (type_code);
    END IF;
END $$;

-- Migration: Add missing columns to users table
-- This adds: respond_user_id, respond_synced, superior_id

-- Add respond_user_id column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'respond_user_id'
    ) THEN
        ALTER TABLE users ADD COLUMN respond_user_id VARCHAR;
    END IF;
END $$;

-- Add respond_synced column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'respond_synced'
    ) THEN
        ALTER TABLE users ADD COLUMN respond_synced VARCHAR NOT NULL DEFAULT 'pending';
    END IF;
END $$;

-- Add superior_id column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'superior_id'
    ) THEN
        ALTER TABLE users ADD COLUMN superior_id VARCHAR;
    END IF;
END $$;

-- Add foreign key constraint for superior_id if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_users_superior_id' AND table_name = 'users'
    ) THEN
        ALTER TABLE users 
        ADD CONSTRAINT fk_users_superior_id 
        FOREIGN KEY (superior_id) REFERENCES users(id);
    END IF;
END $$;

-- Add index for respond_synced if it doesn't exist
CREATE INDEX IF NOT EXISTS users_respond_synced_idx ON users(respond_synced);

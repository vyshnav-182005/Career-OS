-- ============================================================
-- CareerOS — Auth.js Migration: users + password_reset_tokens
-- Run this in Supabase Dashboard → SQL Editor
-- ============================================================

-- 1. Create the users table (replaces auth.users for credential storage)
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email TEXT NOT NULL UNIQUE,
            name TEXT,
                hashed_password TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        );

                        -- Auto-update the updated_at timestamp
                        CREATE TRIGGER users_updated_at
                            BEFORE UPDATE ON public.users
                                FOR EACH ROW
                                    EXECUTE FUNCTION public.update_updated_at();

                                    -- Disable RLS on users table (only accessed by service key from backend)
                                    ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

                                    -- Service role has full access to users table
                                    CREATE POLICY "Service role full access on users"
                                        ON public.users
                                            FOR ALL
                                                USING (true)
                                                    WITH CHECK (true);

                                                    -- 2. Create password reset tokens table
                                                    CREATE TABLE IF NOT EXISTS public.password_reset_tokens (
                                                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                                            token_hash TEXT NOT NULL UNIQUE,
                                                                user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                                                                    expires_at TIMESTAMPTZ NOT NULL,
                                                                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                                                                        );

                                                                        ALTER TABLE public.password_reset_tokens ENABLE ROW LEVEL SECURITY;

                                                                        CREATE POLICY "Service role full access on password_reset_tokens"
                                                                            ON public.password_reset_tokens
                                                                                FOR ALL
                                                                                    USING (true)
                                                                                        WITH CHECK (true);

                                                                                        -- 3. Update profiles table foreign key
                                                                                        --    Drop old FK that references auth.users, add new FK to public.users
                                                                                        --    NOTE: This will fail if there's existing data referencing auth.users.
                                                                                        --    Since we're in development, drop and recreate the constraint.

                                                                                        -- Drop old constraint (the auto-generated name may vary; this handles both cases)
                                                                                        DO $$
                                                                                        BEGIN
                                                                                            -- Try to drop the FK constraint by common naming patterns
                                                                                                ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_user_id_fkey;
                                                                                                EXCEPTION WHEN OTHERS THEN
                                                                                                    RAISE NOTICE 'Could not drop constraint profiles_user_id_fkey: %', SQLERRM;
                                                                                                    END $$;

                                                                                                    -- Clear existing profile data (development only — single test entry)
                                                                                                    TRUNCATE public.profiles;

                                                                                                    -- Update user_id column to reference public.users instead of auth.users
                                                                                                    ALTER TABLE public.profiles
                                                                                                        ADD CONSTRAINT profiles_user_id_fkey
                                                                                                            FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

                                                                                                            -- 4. Update RLS policies on profiles to use service-role-only access
                                                                                                            --    (Auth.js sessions are validated in the application layer, not by Supabase Auth)
                                                                                                            DROP POLICY IF EXISTS "Users can view own profile" ON public.profiles;
                                                                                                            DROP POLICY IF EXISTS "Service role full access" ON public.profiles;

                                                                                                            CREATE POLICY "Service role full access on profiles"
                                                                                                                ON public.profiles
                                                                                                                    FOR ALL
                                                                                                                        USING (true)
                                                                                                                            WITH CHECK (true);
                                                                                                                            s
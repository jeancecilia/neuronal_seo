-- Neuronal SEO Database Initialization
-- This script runs on first PostgreSQL container startup

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create indexes for vector similarity search
-- (These will be created by SQLAlchemy, but we ensure they exist)

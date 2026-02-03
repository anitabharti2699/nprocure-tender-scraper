/*
  # Tender Scraper Database Schema

  ## Overview
  This migration creates the core tables for the nprocure tender scraper system.
  It supports production-grade data persistence with deduplication, audit trails,
  and comprehensive run-level metadata for observability.

  ## 1. New Tables
  
  ### `tenders`
  Stores scraped tender records with normalized, clean data.
  
  Fields:
  - `id` (uuid, primary key) - Internal database ID for referencing
  - `tender_id` (text, indexed) - Stable identifier extracted from source site
  - `source` (text) - Origin identifier (e.g., 'nprocure')
  - `tender_type` (text) - Enum: Goods, Works, or Services
  - `title` (text) - Tender title/heading
  - `organization` (text) - Procuring organization name
  - `publish_date` (date, indexed) - When tender was published (ISO format)
  - `closing_date` (date, nullable, indexed) - Deadline for submissions
  - `description` (text) - Clean description with boilerplate removed
  - `source_url` (text) - Canonical URL for the tender detail page
  - `attachments` (jsonb) - Array of {name, url} objects
  - `raw_data` (jsonb, nullable) - Original scraped data for debugging
  - `created_at` (timestamptz) - When record was first inserted
  - `updated_at` (timestamptz) - When record was last modified
  
  Constraints:
  - Unique constraint on (tender_id, source) for deduplication
  - Check constraint on tender_type enum values
  
  ### `scraper_runs`
  Stores metadata for each scraper execution. Critical for observability,
  debugging, and tracking system health over time.
  
  Fields:
  - `id` (uuid, primary key) - Unique run identifier
  - `run_id` (text, unique) - Human-readable run ID
  - `scraper_version` (text) - Git SHA or version tag
  - `config` (jsonb) - Complete config snapshot (rate, concurrency, limits)
  - `start_time` (timestamptz, indexed) - Execution start timestamp
  - `end_time` (timestamptz, nullable) - Execution completion timestamp
  - `duration_seconds` (numeric, nullable) - Total execution time
  - `status` (text) - Enum: running, completed, failed
  - `pages_visited` (integer) - Count of HTTP requests made
  - `tenders_parsed` (integer) - Successfully parsed tender records
  - `tenders_saved` (integer) - Records written to database
  - `deduped_count` (integer) - Duplicates skipped
  - `failures` (integer) - Count of failed operations
  - `error_summary` (jsonb) - Grouped errors: {error_type: count}
  - `created_at` (timestamptz) - Record creation time
  
  ## 2. Security
  - Enable RLS on both tables
  - Add policies for authenticated access
  
  ## 3. Notes
  - Indexes on frequently queried fields (dates, tender_id) for performance
  - JSONB fields allow flexible storage while maintaining structure
  - Deduplication prevents data pollution from repeated scrapes
  - Error tracking enables proactive monitoring and alerting
*/

-- Create tenders table
CREATE TABLE IF NOT EXISTS tenders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tender_id text NOT NULL,
  source text NOT NULL DEFAULT 'nprocure',
  tender_type text NOT NULL,
  title text NOT NULL,
  organization text NOT NULL,
  publish_date date NOT NULL,
  closing_date date,
  description text NOT NULL,
  source_url text NOT NULL,
  attachments jsonb DEFAULT '[]'::jsonb,
  raw_data jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  CONSTRAINT tender_type_check CHECK (tender_type IN ('Goods', 'Works', 'Services')),
  CONSTRAINT unique_tender UNIQUE (tender_id, source)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tenders_publish_date ON tenders(publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_tenders_closing_date ON tenders(closing_date) WHERE closing_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tenders_tender_id ON tenders(tender_id);
CREATE INDEX IF NOT EXISTS idx_tenders_source ON tenders(source);

-- Create scraper_runs table
CREATE TABLE IF NOT EXISTS scraper_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id text UNIQUE NOT NULL,
  scraper_version text NOT NULL,
  config jsonb NOT NULL,
  start_time timestamptz NOT NULL DEFAULT now(),
  end_time timestamptz,
  duration_seconds numeric,
  status text NOT NULL DEFAULT 'running',
  pages_visited integer DEFAULT 0,
  tenders_parsed integer DEFAULT 0,
  tenders_saved integer DEFAULT 0,
  deduped_count integer DEFAULT 0,
  failures integer DEFAULT 0,
  error_summary jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now(),
  CONSTRAINT status_check CHECK (status IN ('running', 'completed', 'failed'))
);

-- Create index for run queries
CREATE INDEX IF NOT EXISTS idx_scraper_runs_start_time ON scraper_runs(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_scraper_runs_status ON scraper_runs(status);

-- Enable Row Level Security
ALTER TABLE tenders ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper_runs ENABLE ROW LEVEL SECURITY;

-- Create policies for authenticated access
CREATE POLICY "Authenticated users can read tenders"
  ON tenders FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Authenticated users can insert tenders"
  ON tenders FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated users can update tenders"
  ON tenders FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated users can read scraper_runs"
  ON scraper_runs FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Authenticated users can insert scraper_runs"
  ON scraper_runs FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated users can update scraper_runs"
  ON scraper_runs FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

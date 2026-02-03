# Schema Documentation

This document explains the purpose and design rationale for every field in the database schema.

## Table: `tenders`

Stores normalized tender records with full data lineage for debugging and auditing.

### Fields

#### `id` (uuid, primary key)
**Purpose:** Internal database identifier
**Why:** Enables foreign key references and internal operations. Separate from tender_id because tender_id comes from external source and may have collisions across different sources.

#### `tender_id` (text, indexed)
**Purpose:** Stable identifier extracted from source site
**Why:** Enables deduplication across runs. Must be stable across scrapes of the same tender. Used in UNIQUE constraint with source.
**Example:** "TND-2024-001234", "12345", "nprocure-tender-567"

#### `source` (text, indexed)
**Purpose:** Origin identifier (e.g., 'nprocure', 'etenders', 'ungm')
**Why:** Enables multi-source scraping without ID collisions. Same tender_id from different sources are different tenders. Supports future expansion to scrape multiple portals.
**Example:** "nprocure"

#### `tender_type` (text, CHECK constraint)
**Purpose:** Category of procurement (Goods, Works, or Services)
**Why:** Critical for filtering and analysis. Strict enum prevents data quality issues. These three categories are standard across government procurement globally (based on GPA/UNCITRAL Model Law).
**Valid Values:** "Goods", "Works", "Services"
**Use Cases:**
- Filter searches: "show me all Works tenders"
- Analytics: "what % of tenders are Services?"
- Alerts: "notify me of new Goods tenders"

#### `title` (text)
**Purpose:** Tender headline or subject
**Why:** Primary human-readable identifier. Used in search results, alerts, and summaries.
**Example:** "Supply of Medical Equipment for Regional Hospital"

#### `organization` (text)
**Purpose:** Name of procuring entity
**Why:** Enables filtering by buyer. Critical for vendor targeting ("show me all tenders from Ministry of Health"). Supports vendor relationship management.
**Example:** "Ministry of Health and Social Services", "City of Windhoek", "Roads Authority"

#### `publish_date` (date, indexed)
**Purpose:** When tender was first posted (ISO 8601 format: YYYY-MM-DD)
**Why:** Enables time-series analysis, sorting by recency, and tracking publication patterns. Indexed for fast queries like "tenders published in last 7 days".
**Use Cases:**
- Freshness filtering: "show new tenders from last week"
- Trend analysis: "tenders published per month over time"
- Alert freshness: "notify of tenders published after my last check"

#### `closing_date` (date, nullable, indexed)
**Purpose:** Deadline for tender submissions (ISO 8601 format: YYYY-MM-DD)
**Why:** Critical for vendors to know response deadline. Nullable because some tenders are open-ended or have rolling deadlines. Indexed for urgency queries.
**Use Cases:**
- Urgency filtering: "tenders closing in next 7 days"
- Overdue detection: "tenders past closing date"
- Time-to-respond calculation: closing_date - current_date

#### `description` (text)
**Purpose:** Clean, normalized tender description with boilerplate removed
**Why:** Provides context for decision-making. Cleaned to remove navigation text, disclaimers, and repeated boilerplate that pollutes search and analysis. Whitespace normalized for readability.
**Cleaning Applied:**
- Remove boilerplate phrases like "This is a tender notice"
- Collapse multiple spaces/newlines
- Strip leading/trailing whitespace
- Remove HTML artifacts

#### `source_url` (text)
**Purpose:** Canonical URL to original tender detail page
**Why:** Enables verification, manual review, and access to latest updates. Acts as unique identifier and audit trail. Critical for compliance (must be able to trace data to source).
**Example:** "https://tender.nprocure.com/tender/details/12345"

#### `attachments` (jsonb)
**Purpose:** List of document files (PDFs, specs, drawings)
**Format:** `[{"name": "Technical Specifications.pdf", "url": "https://..."}, ...]`
**Why:** Documents contain critical details (technical specs, eligibility criteria, bid forms). JSONB allows flexible structure while maintaining queryability. Can query for tenders with/without attachments.
**Use Cases:**
- Check if tender has downloadable specs
- Automated document download pipeline
- Attachment count as data quality signal

#### `raw_data` (jsonb, nullable)
**Purpose:** Original scraped data before cleaning
**Why:** Essential for debugging parsing issues, validating cleaning logic, and recovering from bugs. Enables retroactive reprocessing if cleaning logic improves. Acts as audit trail.
**Use Cases:**
- Debugging: "why did this field parse incorrectly?"
- Validation: "did we lose any information during cleaning?"
- Reprocessing: "re-clean all descriptions with improved boilerplate detection"

#### `created_at` (timestamptz)
**Purpose:** When record was first inserted into database
**Why:** Audit trail for when we discovered this tender. Different from publish_date (when tender was posted on site). Enables analysis like "how fast do we detect new tenders after publication?"

#### `updated_at` (timestamptz)
**Purpose:** When record was last modified
**Why:** Track changes over time. If we re-scrape a tender and data changed, updated_at reflects when we noticed. Useful for debugging and change detection.

### Constraints

#### UNIQUE (tender_id, source)
**Purpose:** Prevent duplicate tenders from same source
**Why:** Idempotent writes. Running scraper multiple times won't create duplicates. Enables upsert pattern.

#### CHECK (tender_type IN ('Goods', 'Works', 'Services'))
**Purpose:** Enforce valid tender types
**Why:** Data quality. Prevents typos and ensures consistent categorization for reliable filtering and analysis.

### Indexes

#### `idx_tenders_publish_date` (publish_date DESC)
**Purpose:** Fast queries for recent tenders
**Why:** Most common query pattern is "show me latest tenders". DESC order supports this directly.

#### `idx_tenders_closing_date` (closing_date)
**Purpose:** Fast queries for urgent tenders
**Why:** "Tenders closing soon" is critical vendor use case. Filtered to only index non-null closing dates.

#### `idx_tenders_tender_id` (tender_id)
**Purpose:** Fast lookups by tender ID
**Why:** Deduplication check before insert. Also supports external API queries like "get tender by ID".

#### `idx_tenders_source` (source)
**Purpose:** Fast filtering by source
**Why:** Multi-source deployments need to filter/aggregate by source. Supports future expansion.

---

## Table: `scraper_runs`

Tracks metadata for each scraper execution. Critical for observability, debugging, and long-term system health monitoring.

### Fields

#### `id` (uuid, primary key)
**Purpose:** Internal database identifier
**Why:** Standard primary key for database operations.

#### `run_id` (text, unique)
**Purpose:** Human-readable unique identifier for this run
**Why:** Used in logs and for tracing. Easier to reference in conversations than UUID. Example: "check logs for run abc123". Currently uses UUID but could be extended to semantic IDs like "scrape-2024-01-15-001".

#### `scraper_version` (text)
**Purpose:** Git commit SHA or version tag
**Why:** Essential for debugging. If behavior changes between runs, version helps identify code changes. Supports rollback decisions ("version X had higher error rate"). Enables reproducibility.
**Example:** "1.0.0", "a1b2c3d", "v2.3.1"

#### `config` (jsonb)
**Purpose:** Complete configuration snapshot
**Format:** `{"rate_limit": 1.0, "timeout": 30, "retries": 3, "limit": null, ...}`
**Why:** Reproducibility. Must be able to answer "why did this run behave differently?" Configuration changes explain performance differences. JSONB allows flexible config without schema changes.
**Use Cases:**
- Compare runs: "run A had 10 failures, run B had 100 - B used 0.1s timeout vs A's 30s"
- Optimization: "does increasing rate limit increase error rate?"
- Debugging: "did someone accidentally set limit=10?"

#### `start_time` (timestamptz, indexed)
**Purpose:** When scraper execution began
**Why:** Enables time-series analysis of scraper runs. Combined with end_time, calculates duration. Indexed for "show recent runs" queries.

#### `end_time` (timestamptz, nullable)
**Purpose:** When scraper execution completed
**Why:** Null if scraper crashed or is still running. Combined with start_time, calculates total duration. Enables crash detection ("run started but never ended").

#### `duration_seconds` (numeric, nullable)
**Purpose:** Total execution time in seconds
**Why:** Key performance metric. Denormalized from (end_time - start_time) for easier querying and aggregation. Enables performance analysis: "why are runs getting slower?" Null if run hasn't completed.
**Use Cases:**
- Performance tracking: "average run duration over time"
- Anomaly detection: "flag runs > 2x median duration"
- Capacity planning: "if we scrape hourly, will runs overlap?"

#### `status` (text, CHECK constraint)
**Purpose:** Run outcome (running, completed, failed)
**Why:** High-level health indicator. Enables filtering ("show me failed runs") and success rate calculation. Strict enum for data quality.
**Valid Values:**
- "running": In progress (or crashed without cleanup)
- "completed": Finished successfully
- "failed": Fatal error or user interrupt

#### `pages_visited` (integer)
**Purpose:** Count of HTTP requests made
**Why:** Throughput metric. Helps diagnose performance ("run was slow because we visited 1000 pages vs usual 100"). Detects pagination issues. Enables rate calculation (pages/second).
**Use Cases:**
- Detect infinite pagination loops
- Calculate cost (if using proxy service charged per request)
- Performance analysis: duration / pages_visited = seconds per page

#### `tenders_parsed` (integer)
**Purpose:** Count of tenders successfully extracted from HTML
**Why:** Quality metric. Low ratio of parsed/visited suggests HTML structure changed or parser broke. Tracks gross throughput before validation.
**Interpretation:** tenders_parsed < expected → parsing is broken

#### `tenders_saved` (integer)
**Purpose:** Count of tenders written to database
**Why:** Net throughput metric. What actually made it into the system. Combined with tenders_parsed, calculates validation pass rate. This is the key success metric.
**Use Cases:**
- Success metric: "scraper saved 450 new tenders today"
- Alert threshold: "alert if tenders_saved < 100"

#### `deduped_count` (integer)
**Purpose:** Count of duplicate tenders skipped
**Why:** Efficiency and behavior metric. High dedup on first run suggests historical backfill. High dedup on subsequent runs suggests stable dataset. Zero dedup might indicate tender_id extraction broke.
**Use Cases:**
- Detect broken deduplication: deduped_count = 0 when it should be high
- Estimate incremental scrapers: "only 5% new tenders per run"
- Data quality: "100% dedup rate means we're not finding anything new"

#### `failures` (integer)
**Purpose:** Total count of failed operations (fetch, parse, save)
**Why:** Reliability metric. Combined with success counts, calculates error rate. Spike in failures indicates site changes or anti-bot measures.
**Alert:** failures > (0.1 * pages_visited) → high error rate

#### `error_summary` (jsonb)
**Purpose:** Grouped error counts by type
**Format:** `{"fetch_error": 12, "parse_error": 5, "timeout": 3}`
**Why:** Root cause analysis. Not just "10 errors" but "10 fetch errors". Enables targeted fixes. JSONB allows flexible error types without schema changes.
**Use Cases:**
- Debugging: "all errors are 'timeout' → increase timeout setting"
- Prioritization: "parse_error is most common → fix parser first"
- Monitoring: "alert if any single error type > 20% of total"

#### `created_at` (timestamptz)
**Purpose:** When record was created
**Why:** Standard audit field. Usually same as start_time but could differ if run is logged retroactively.

### Constraints

#### CHECK (status IN ('running', 'completed', 'failed'))
**Purpose:** Enforce valid status values
**Why:** Data quality for reliable filtering and aggregation.

### Indexes

#### `idx_scraper_runs_start_time` (start_time DESC)
**Purpose:** Fast queries for recent runs
**Why:** Most common query is "show latest runs". DESC supports this directly.

#### `idx_scraper_runs_status` (status)
**Purpose:** Fast filtering by status
**Why:** Common queries: "show failed runs", "count completed runs today".

---

## How Metadata Enables Observability

### Key Questions Metadata Answers

1. **Is the scraper healthy?**
   - Query: Recent runs with status='completed' and low failure rate
   - Metric: success_rate = tenders_saved / tenders_parsed

2. **Is performance degrading?**
   - Query: duration_seconds trend over time
   - Metric: pages_visited / duration_seconds

3. **Is the site blocking us?**
   - Query: error_summary contains 'fetch_error' or 'timeout'
   - Metric: failures / pages_visited ratio

4. **Is our parser broken?**
   - Query: tenders_parsed dropped significantly
   - Metric: tenders_parsed / pages_visited (should be stable)

5. **Are we getting new data?**
   - Query: deduped_count vs tenders_saved ratio
   - Metric: tenders_saved / (tenders_saved + deduped_count)

6. **What changed between runs?**
   - Query: Compare config and scraper_version between runs
   - Diff: config[run_a] vs config[run_b]

### Alerting Rules (Examples)

```sql
-- Alert if scraper fails
SELECT * FROM scraper_runs
WHERE status = 'failed'
  AND start_time > now() - interval '1 hour';

-- Alert if error rate > 10%
SELECT * FROM scraper_runs
WHERE failures::float / NULLIF(pages_visited, 0) > 0.1
  AND start_time > now() - interval '1 day';

-- Alert if no new tenders in 24h
SELECT * FROM scraper_runs
WHERE start_time > now() - interval '24 hours'
GROUP BY date_trunc('day', start_time)
HAVING SUM(tenders_saved) = 0;

-- Alert if runs taking 2x longer than median
WITH stats AS (
  SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_seconds) as median
  FROM scraper_runs
  WHERE status = 'completed'
    AND start_time > now() - interval '7 days'
)
SELECT r.* FROM scraper_runs r, stats
WHERE r.duration_seconds > 2 * stats.median
  AND r.start_time > now() - interval '1 hour';
```

## Data Quality Guarantees

### Enforced by Database

1. **No duplicate tenders per source** (UNIQUE constraint)
2. **Valid tender types** (CHECK constraint)
3. **Valid run statuses** (CHECK constraint)
4. **Non-null required fields** (NOT NULL constraints)

### Enforced by Application

1. **ISO 8601 date format** (cleaner.py validates and normalizes)
2. **Collapsed whitespace** (cleaner.py normalizes)
3. **Non-empty required fields** (cleaner.py validates)
4. **Boilerplate-free descriptions** (cleaner.py strips patterns)

### Not Enforced (By Design)

1. **Closing date > publish date**: Some tenders have retroactive publication
2. **URL format validation**: External URLs may change format
3. **Description length limits**: Some tenders have very long descriptions
4. **Organization name standardization**: Names vary ("MoH" vs "Ministry of Health")

## Schema Evolution

If fields need to be added:

1. **To tenders table:**
   - Add nullable column (safe, no data migration needed)
   - Update cleaner.py to populate new field
   - Update parser.py to extract new field
   - Re-run scraper to populate historical data from raw_data

2. **To scraper_runs table:**
   - Add nullable column (safe)
   - Update tracker.py to record new metric
   - Future runs will have the field, historical runs will be null

**Why JSONB fields help:**
- raw_data can be reprocessed if we missed something
- config and error_summary are extensible without migrations
- Enables rapid iteration on metadata collection

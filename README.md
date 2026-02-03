# nprocure Tender Scraper

Production-grade web scraper for extracting tender data from https://tender.nprocure.com/

## Features

- **Reliable**: Exponential backoff retries, graceful error handling, comprehensive logging
- **Respectful**: Configurable rate limiting, realistic User-Agent headers
- **Observable**: Full run-level metadata, error tracking, performance metrics
- **Idempotent**: Duplicate detection prevents data pollution from repeated runs
- **Production-Ready**: Structured data persistence with Supabase PostgreSQL

## Requirements

- Python 3.10+
- Supabase account (free tier sufficient)
- Internet connection

## Setup

### 1. Clone and Install

```bash
# Install Python dependencies
pip install -r requirements.txt
```

### 2. Configure Supabase

The database schema is already created. Your `.env` file should contain:

```
SUPABASE_URL=your_supabase_project_url
SUPABASE_ANON_KEY=your_supabase_anon_key
```

If you need to set up a new Supabase project:

1. Create account at https://supabase.com
2. Create new project
3. Copy URL and anon key to `.env` file
4. Run the migration in `supabase/migrations/` via Supabase dashboard

### 3. Verify Setup

```bash
# Test database connection
python -c "from store import TenderStorage; storage = TenderStorage(); print(storage.get_stats())"
```

Expected output: `{'total_tenders': 0, 'source': 'nprocure'}`

## Usage

### Basic Usage

```bash
# Scrape with default settings (1 req/sec, max 10 pages)
python scrape.py
```

### Common Options

```bash
# Scrape first 50 tenders
python scrape.py --limit 50

# Faster scraping (3 requests per second)
python scrape.py --rate-limit 3.0

# Scrape more pages
python scrape.py --max-pages 50

# Verbose logging for debugging
python scrape.py --verbose

# Combine options
python scrape.py --limit 100 --rate-limit 2.0 --max-pages 20 --verbose
```

### Full Options

```
Options:
  --rate-limit FLOAT    Requests per second (default: 1.0)
  --timeout INT         Request timeout in seconds (default: 30)
  --retries INT         Max retries per request (default: 3)
  --limit INT           Maximum number of tenders to scrape (default: no limit)
  --max-pages INT       Maximum listing pages to scrape (default: 10)
  --base-url URL        Base URL of tender site (default: https://tender.nprocure.com)
  --verbose             Enable verbose logging
  -h, --help            Show this help message
```

## Output

### Database Tables

Data is stored in two Supabase tables:

**tenders**: Scraped tender records
```sql
SELECT tender_id, title, organization, tender_type, publish_date, closing_date
FROM tenders
ORDER BY publish_date DESC
LIMIT 10;
```

**scraper_runs**: Execution metadata
```sql
SELECT run_id, start_time, duration_seconds, tenders_saved, deduped_count, failures
FROM scraper_runs
ORDER BY start_time DESC
LIMIT 10;
```

### Logs

Structured logs are written to stdout:

```
2024-01-15 10:23:45 [INFO] __main__: Starting nprocure tender scraper
2024-01-15 10:23:45 [INFO] metadata.tracker: Started run abc123-def456
2024-01-15 10:23:46 [INFO] __main__: Fetching page 1
2024-01-15 10:23:47 [INFO] parse.parser: Parsed 15 tenders from listing page
2024-01-15 10:24:32 [INFO] __main__: Saved 15 tenders, skipped 0 duplicates, 0 failures
2024-01-15 10:24:32 [INFO] metadata.tracker: Run abc123-def456 completed: 15 saved, 0 deduped, 0 failures in 47.2s
```

## Project Structure

```
.
├── scrape.py              # Main CLI entry point
├── fetch/
│   └── fetcher.py        # HTTP client with retry logic
├── parse/
│   └── parser.py         # HTML extraction
├── clean/
│   └── cleaner.py        # Data normalization and validation
├── store/
│   └── storage.py        # Supabase persistence
├── metadata/
│   └── tracker.py        # Run tracking and metrics
├── architecture.md        # Design decisions and tradeoffs
├── schema.md             # Field-by-field documentation
├── sample-output.json    # Example scraped data
└── requirements.txt      # Python dependencies
```

## Data Quality

The scraper ensures:

- **Normalized dates**: All dates in ISO 8601 format (YYYY-MM-DD)
- **Clean text**: Boilerplate removed, whitespace collapsed
- **Strict types**: tender_type validated against enum (Goods, Works, Services)
- **No duplicates**: UNIQUE constraint on (tender_id, source)
- **Required fields**: Validation ensures no missing critical data

## Monitoring

### Check Scraper Health

```sql
-- Recent run statistics
SELECT
  run_id,
  start_time,
  duration_seconds,
  tenders_saved,
  deduped_count,
  failures,
  ROUND(100.0 * failures / NULLIF(pages_visited, 0), 2) as error_rate_pct
FROM scraper_runs
ORDER BY start_time DESC
LIMIT 10;
```

### Alert Conditions

- `status = 'failed'`: Scraper crashed
- `failures > 0.1 * pages_visited`: High error rate (>10%)
- `tenders_saved = 0`: No new data found
- `duration_seconds > 2 * median_duration`: Slow run

### Error Analysis

```sql
-- Group errors by type
SELECT
  run_id,
  start_time,
  jsonb_each_text(error_summary) as error_breakdown
FROM scraper_runs
WHERE failures > 0
ORDER BY start_time DESC;
```

## Troubleshooting

### "SUPABASE_URL and SUPABASE_ANON_KEY must be set"

- Ensure `.env` file exists in project root
- Check that variable names are correct (not `VITE_SUPABASE_URL`)
- Verify `.env` is loaded: `python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('SUPABASE_URL'))"`

### "Failed to fetch page X"

- Site may be down or blocking requests
- Try increasing `--timeout` to 60 seconds
- Decrease `--rate-limit` to 0.5 (slower but more respectful)
- Check site accessibility in browser

### "No tenders found on page 1"

- Site HTML structure may have changed
- Run with `--verbose` to see detailed logs
- Inspect HTML selectors in `parse/parser.py`
- Update selectors to match current site structure

### High duplicate rate

- Normal after first full scrape
- Subsequent runs will mostly find duplicates
- To scrape fresh data, try scraping with filters or different pages

### Slow performance

- Network latency is primary bottleneck
- Increase `--rate-limit` carefully (don't overload site)
- Consider scraping during off-peak hours
- Check `duration_seconds / pages_visited` ratio in scraper_runs

## Development

### Update HTML Selectors

When site structure changes, update selectors in `parse/parser.py`:

1. Inspect site HTML in browser DevTools
2. Update CSS selectors in `_extract_*` methods
3. Test with `--limit 5 --verbose`
4. Commit changes with description of what changed

### Add New Field

To extract additional data:

1. Update `parse/parser.py` to extract field
2. Update `clean/cleaner.py` to normalize field
3. Add database migration for new column
4. Update schema.md to document purpose

## Performance

**Typical Performance** (with default settings):
- Rate limit: 1 req/sec
- ~30 tenders per page
- ~2 pages per minute
- ~60 tenders per minute
- ~1000 tenders in 15-20 minutes

**Optimized Performance** (careful use):
- Rate limit: 3 req/sec
- ~180 tenders per minute
- ~1000 tenders in 5-6 minutes

## Security

- Secrets stored in `.env` file (gitignored)
- No execution of scraped content
- Row-Level Security enabled on all tables
- Parameterized queries prevent SQL injection
- Minimal User-Agent spoofing (identifies as browser)

## License

This scraper is for authorized use only. Respect the target site's robots.txt and terms of service.

## Documentation

- **architecture.md**: Design decisions, tradeoffs, and alternatives considered
- **schema.md**: Detailed field-by-field documentation with use cases
- **sample-output.json**: Example of scraped tender data

## Support

For issues:
1. Check logs with `--verbose` flag
2. Query `scraper_runs` table for error details
3. Verify site is accessible in browser
4. Check if HTML selectors need updating

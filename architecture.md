# Architecture Documentation

## Overview

This scraper uses a **hybrid HTML-first approach** with modular design for production-grade reliability. The architecture prioritizes maintainability, observability, and resilience over cleverness.

## Architectural Decisions

### 1. HTML Scraping vs API vs Hybrid

**Decision: HTML Scraping (with API fallback capability)**

**Rationale:**
- nprocure.com appears to be a server-rendered HTML portal (based on timeout during initial analysis)
- Most government tender portals use traditional HTML rendering for accessibility compliance
- HTML parsing is more stable than unofficial API endpoints that may change without notice
- The codebase is structured to easily switch to API mode if endpoints are discovered

**Tradeoffs:**
- **Pros:**
  - Works with the actual public interface that's less likely to change
  - No need to reverse-engineer or maintain API authentication
  - Selectors can be updated independently if layout changes
- **Cons:**
  - Slightly more parsing overhead than JSON APIs
  - More brittle to HTML structure changes
  - Requires more sophisticated parsing logic

**Alternative Considered:**
- Pure API approach would be faster but requires discovery of undocumented endpoints
- Headless browser (Selenium/Playwright) would handle JS rendering but adds massive overhead
- This architecture allows easy migration to API-first if endpoints are discovered

### 2. Module Separation

**Decision: Strict separation into fetch/ parse/ clean/ store/ metadata/**

**Rationale:**
- Single Responsibility Principle: each module has one reason to change
- Enables independent testing and debugging of each layer
- Makes it obvious where to look when issues arise
- Facilitates parallel development and code reviews

**Module Responsibilities:**
- `fetch/`: HTTP concerns (rate limiting, retries, timeouts)
- `parse/`: HTML/JSON extraction (no business logic)
- `clean/`: Data normalization and validation (no I/O)
- `store/`: Persistence layer (deduplication, transactions)
- `metadata/`: Observability and run tracking

### 3. Database Choice: Supabase

**Decision: Supabase PostgreSQL**

**Rationale:**
- Production-ready managed PostgreSQL with automatic backups
- JSONB support for flexible metadata storage
- Built-in auth and RLS for security
- Real-time subscriptions available for future monitoring dashboard
- Easy to query with standard SQL for analysis

**Tradeoffs:**
- **Pros:**
  - Battle-tested relational database
  - ACID compliance prevents data corruption
  - Powerful query capabilities (JOINs, aggregations, indexes)
  - Simple migration path to self-hosted PostgreSQL if needed
- **Cons:**
  - Requires network connection (not suitable for offline operation)
  - Slightly more setup than SQLite

**Alternative Considered:**
- SQLite would work for local-only operation but lacks concurrency
- MongoDB would be simpler for schema flexibility but worse for relational queries

### 4. Error Handling Strategy

**Decision: Graceful degradation with comprehensive logging**

**Rationale:**
- Scraper should never crash on a single bad page
- All errors are logged with context (tender_id, URL, error type)
- Errors are aggregated in metadata for pattern detection
- Failed items are skipped but counted

**Implementation:**
- Try-except blocks at every I/O boundary
- Exponential backoff on retries (prevents thundering herd)
- Circuit breaker pattern: stop pagination if too many consecutive failures
- Errors grouped by type in metadata for root cause analysis

### 5. Rate Limiting Approach

**Decision: Client-side rate limiting with configurable delay**

**Rationale:**
- Respectful scraping: don't overload the target server
- Prevents IP blocks or CAPTCHA challenges
- Configurable via CLI for different environments (dev/prod)

**Implementation:**
- Simple time-based throttling between requests
- Default 1 req/sec is conservative but safe
- Exponential backoff on retries adds natural rate limiting

### 6. Deduplication Strategy

**Decision: Database-level UNIQUE constraint on (tender_id, source)**

**Rationale:**
- Prevents data pollution from repeated runs
- Idempotent writes: running scraper multiple times is safe
- Database enforces uniqueness atomically (no race conditions)
- Upsert pattern allows updating existing records

**Implementation:**
- Pre-check existing IDs before insert (reduces failed inserts)
- Track deduped count in metadata for observability
- Original scraped data stored in raw_data JSONB for debugging

### 7. Configuration Management

**Decision: Environment variables + CLI arguments**

**Rationale:**
- 12-factor app principles: config separate from code
- Secrets (API keys) in .env file, never committed
- Operational params (rate limit, timeout) via CLI for easy tuning
- Config snapshot stored in metadata for reproducibility

### 8. Logging and Observability

**Decision: Structured logging + run-level metadata table**

**Rationale:**
- Structured logs enable log aggregation and analysis
- Metadata table provides historical view of scraper health
- Each run gets unique ID for tracing issues
- Error summary enables proactive alerting

**Key Metrics Tracked:**
- Throughput: tenders/second, pages/second
- Quality: parse success rate, validation pass rate
- Reliability: error rate by type, retry counts
- Efficiency: duplicate rate, time per page

## Data Flow

```
1. CLI → Configure scraper with rate limits, timeouts, etc.
2. Fetcher → HTTP GET listing page with retry logic
3. Parser → Extract tender links and basic info from HTML
4. For each tender:
   a. Fetcher → GET detail page
   b. Parser → Extract full tender data
   c. Cleaner → Normalize dates, types, text
   d. Storage → Upsert to database (skip if duplicate)
5. Tracker → Finalize run metadata with statistics
```

## Scalability Considerations

**Current Limitations:**
- Single-threaded execution (simple, predictable)
- Rate limiting prevents parallel requests
- Suitable for ~1000s of tenders

**Future Improvements (if needed):**
- Use asyncio for concurrent detail page fetching (10-100x faster)
- Implement batch processing for database writes
- Add distributed queue (Celery/RQ) for horizontal scaling
- Use caching layer (Redis) for deduplication checks

**Why Not Implemented Now:**
- YAGNI principle: build what's needed, not what might be needed
- Single-threaded is easier to debug and reason about
- Most tender portals have 100s-1000s of tenders, not millions
- Rate limiting makes concurrency less beneficial

## Security Considerations

- Secrets managed via environment variables (never hardcoded)
- User-Agent spoofing is minimal (identifies as browser, not bot)
- Row-Level Security (RLS) enabled on all database tables
- No execution of scraped content (pure data extraction)
- SQL injection prevented by parameterized queries (Supabase SDK)

## Maintenance and Debugging

**When HTML structure changes:**
1. Run scraper with --verbose flag
2. Check parser.py selectors against current HTML
3. Update selectors in _extract_* methods
4. Test against sample HTML

**When error rate increases:**
1. Query scraper_runs table for error_summary
2. Group by error type to identify pattern
3. Check if site structure changed or anti-bot measures added
4. Adjust rate limiting or retry logic

**When duplicates increase:**
1. Check if tender_id extraction logic is stable
2. Verify URL patterns haven't changed
3. Inspect raw_data field for troubleshooting

## Testing Strategy

**Current Status: No automated tests (per requirements)**

**Recommended for Production:**
- Unit tests for cleaner.py (pure functions, easy to test)
- Integration tests with sample HTML fixtures
- End-to-end test against staging environment
- Schema validation tests for database

## Performance Profile

**Expected Performance (conservative estimates):**
- 1 req/sec rate limit → 60 pages/minute
- ~10 tenders/page → 600 tenders/minute
- Each tender requires detail page → 30 tenders/minute net
- 1000 tenders → ~33 minutes

**Bottlenecks:**
1. Network I/O (rate limiting)
2. HTML parsing (negligible compared to network)
3. Database writes (batched, fast)

**Optimization Opportunities:**
- Increase rate limit if site can handle it
- Use async HTTP for concurrent fetching
- Cache listing pages for development

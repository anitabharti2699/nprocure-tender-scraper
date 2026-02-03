import os
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from collections import defaultdict
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class RunTracker:
    """
    Tracks scraper run metadata for observability and debugging.
    Records configuration, statistics, and errors for each execution.
    """

    def __init__(self, config: Dict[str, Any], version: str = "1.0.0"):
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_ANON_KEY')

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")

        self.client: Client = create_client(supabase_url, supabase_key)

        self.run_id = str(uuid.uuid4())
        self.config = config
        self.version = version
        self.start_time = datetime.utcnow()

        self.pages_visited = 0
        self.tenders_parsed = 0
        self.tenders_saved = 0
        self.deduped_count = 0
        self.failures = 0
        self.error_summary = defaultdict(int)

    def start_run(self):
        """Initialize run record in database."""
        try:
            record = {
                'run_id': self.run_id,
                'scraper_version': self.version,
                'config': self.config,
                'start_time': self.start_time.isoformat(),
                'status': 'running',
                'pages_visited': 0,
                'tenders_parsed': 0,
                'tenders_saved': 0,
                'deduped_count': 0,
                'failures': 0,
                'error_summary': {}
            }

            self.client.table('scraper_runs').insert(record).execute()
            logger.info(f"Started run {self.run_id}")

        except Exception as e:
            logger.error(f"Error starting run: {e}")

    def increment_pages(self, count: int = 1):
        """Increment pages visited counter."""
        self.pages_visited += count

    def increment_parsed(self, count: int = 1):
        """Increment tenders parsed counter."""
        self.tenders_parsed += count

    def increment_saved(self, count: int = 1):
        """Increment tenders saved counter."""
        self.tenders_saved += count

    def increment_deduped(self, count: int = 1):
        """Increment deduped counter."""
        self.deduped_count += count

    def record_error(self, error_type: str):
        """Record an error occurrence."""
        self.failures += 1
        self.error_summary[error_type] += 1

    def update_stats(self, stats: Dict[str, int]):
        """Bulk update statistics."""
        if 'parsed' in stats:
            self.tenders_parsed += stats['parsed']
        if 'saved' in stats:
            self.tenders_saved += stats['saved']
        if 'deduped' in stats:
            self.deduped_count += stats['deduped']
        if 'failed' in stats:
            self.failures += stats['failed']

    def complete_run(self, status: str = 'completed'):
        """Mark run as complete and persist final statistics."""
        end_time = datetime.utcnow()
        duration = (end_time - self.start_time).total_seconds()

        try:
            update_data = {
                'end_time': end_time.isoformat(),
                'duration_seconds': duration,
                'status': status,
                'pages_visited': self.pages_visited,
                'tenders_parsed': self.tenders_parsed,
                'tenders_saved': self.tenders_saved,
                'deduped_count': self.deduped_count,
                'failures': self.failures,
                'error_summary': dict(self.error_summary)
            }

            self.client.table('scraper_runs').update(update_data).eq(
                'run_id', self.run_id
            ).execute()

            logger.info(
                f"Run {self.run_id} completed: "
                f"{self.tenders_saved} saved, "
                f"{self.deduped_count} deduped, "
                f"{self.failures} failures in {duration:.1f}s"
            )

        except Exception as e:
            logger.error(f"Error completing run: {e}")

    def get_summary(self) -> Dict[str, Any]:
        """Get current run statistics summary."""
        return {
            'run_id': self.run_id,
            'version': self.version,
            'config': self.config,
            'start_time': self.start_time.isoformat(),
            'pages_visited': self.pages_visited,
            'tenders_parsed': self.tenders_parsed,
            'tenders_saved': self.tenders_saved,
            'deduped_count': self.deduped_count,
            'failures': self.failures,
            'error_summary': dict(self.error_summary)
        }

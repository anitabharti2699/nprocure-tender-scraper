import os
import logging
from typing import Dict, Any, List, Optional
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class TenderStorage:
    """
    Handles persistence of tender data to Supabase.
    Implements idempotent writes and deduplication.
    """

    def __init__(self):
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_ANON_KEY')

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")

        self.client: Client = create_client(supabase_url, supabase_key)
        self.source = 'nprocure'

    def save_tender(self, tender: Dict[str, Any], raw_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Save a single tender to database.
        Returns True if saved, False if duplicate or error.
        """
        try:
            record = {
                'tender_id': tender['tender_id'],
                'source': self.source,
                'tender_type': tender['tender_type'],
                'title': tender['title'],
                'organization': tender['organization'],
                'publish_date': tender['publish_date'],
                'closing_date': tender.get('closing_date'),
                'description': tender['description'],
                'source_url': tender['source_url'],
                'attachments': tender.get('attachments', []),
                'raw_data': raw_data,
            }

            result = self.client.table('tenders').upsert(
                record,
                on_conflict='tender_id,source'
            ).execute()

            if result.data:
                logger.debug(f"Saved tender {tender['tender_id']}")
                return True
            else:
                logger.warning(f"Failed to save tender {tender['tender_id']}")
                return False

        except Exception as e:
            logger.error(f"Error saving tender {tender.get('tender_id')}: {e}")
            return False

    def save_tenders_batch(self, tenders: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Save multiple tenders in batch.
        Returns counts: saved, failed, duplicates.
        """
        stats = {
            'saved': 0,
            'failed': 0,
            'deduped': 0
        }

        existing_ids = self._get_existing_tender_ids([t['tender_id'] for t in tenders])

        for tender in tenders:
            if tender['tender_id'] in existing_ids:
                stats['deduped'] += 1
                continue

            if self.save_tender(tender):
                stats['saved'] += 1
            else:
                stats['failed'] += 1

        return stats

    def _get_existing_tender_ids(self, tender_ids: List[str]) -> set:
        """Check which tender IDs already exist in database."""
        if not tender_ids:
            return set()

        try:
            result = self.client.table('tenders').select('tender_id').in_(
                'tender_id', tender_ids
            ).eq('source', self.source).execute()

            return {row['tender_id'] for row in result.data}

        except Exception as e:
            logger.error(f"Error checking existing tenders: {e}")
            return set()

    def get_tender(self, tender_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a tender by ID."""
        try:
            result = self.client.table('tenders').select('*').eq(
                'tender_id', tender_id
            ).eq('source', self.source).maybeSingle().execute()

            return result.data

        except Exception as e:
            logger.error(f"Error retrieving tender {tender_id}: {e}")
            return None

    def get_recent_tenders(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get most recently published tenders."""
        try:
            result = self.client.table('tenders').select('*').eq(
                'source', self.source
            ).order('publish_date', desc=True).limit(limit).execute()

            return result.data

        except Exception as e:
            logger.error(f"Error retrieving recent tenders: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        try:
            total_result = self.client.table('tenders').select(
                'id', count='exact'
            ).eq('source', self.source).execute()

            total = total_result.count if hasattr(total_result, 'count') else 0

            return {
                'total_tenders': total,
                'source': self.source
            }

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {'total_tenders': 0, 'source': self.source}

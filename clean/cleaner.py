import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class DataCleaner:
    """
    Normalizes and validates scraped tender data.
    Ensures data quality and consistency before storage.
    """

    BOILERPLATE_PATTERNS = [
        r'(?i)this\s+is\s+an?\s+tender\s+notice',
        r'(?i)please\s+read\s+carefully',
        r'(?i)important\s+notice:?\s*',
        r'(?i)disclaimer:?\s*',
        r'(?i)terms\s+and\s+conditions:?\s*',
        r'(?i)for\s+more\s+information\s+visit',
        r'(?i)copyright\s+©?\s*\d{4}',
    ]

    TENDER_TYPES = {'Goods', 'Works', 'Services'}

    def clean_tender(self, tender: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Clean and validate a single tender record.
        Returns None if validation fails.
        """
        try:
            cleaned = {
                'tender_id': self._clean_tender_id(tender.get('tender_id')),
                'title': self._clean_text(tender.get('title')),
                'organization': self._clean_text(tender.get('organization')),
                'tender_type': self._clean_tender_type(tender.get('tender_type')),
                'publish_date': self._clean_date(tender.get('publish_date')),
                'closing_date': self._clean_date(tender.get('closing_date')),
                'description': self._clean_description(tender.get('description')),
                'source_url': tender.get('source_url'),
                'attachments': self._clean_attachments(tender.get('attachments', [])),
            }

            if not self._validate_required_fields(cleaned):
                logger.warning(f"Tender {cleaned.get('tender_id')} failed validation")
                return None

            return cleaned

        except Exception as e:
            logger.error(f"Error cleaning tender: {e}")
            return None

    def _clean_tender_id(self, tender_id: Any) -> Optional[str]:
        """Ensure tender_id is a non-empty string."""
        if not tender_id:
            return None
        return str(tender_id).strip()

    def _clean_text(self, text: Any) -> Optional[str]:
        """Normalize text: collapse whitespace, strip, convert empty to None."""
        if not text:
            return None

        text = str(text)
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        return text if text else None

    def _clean_description(self, description: Any) -> Optional[str]:
        """Clean description: remove boilerplate, normalize whitespace."""
        if not description:
            return None

        text = str(description)

        for pattern in self.BOILERPLATE_PATTERNS:
            text = re.sub(pattern, '', text)

        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        text = text.strip()

        return text if text else None

    def _clean_tender_type(self, tender_type: Any) -> Optional[str]:
        """
        Normalize tender type to strict enum: Goods, Works, or Services.
        Uses fuzzy matching for common variations.
        """
        if not tender_type:
            return None

        tender_type = str(tender_type).strip()

        type_lower = tender_type.lower()

        if 'goods' in type_lower or 'supply' in type_lower or 'procurement' in type_lower:
            return 'Goods'
        elif 'works' in type_lower or 'construction' in type_lower or 'building' in type_lower:
            return 'Works'
        elif 'services' in type_lower or 'consulting' in type_lower or 'service' in type_lower:
            return 'Services'

        if tender_type in self.TENDER_TYPES:
            return tender_type

        logger.warning(f"Unknown tender type: {tender_type}, defaulting to Services")
        return 'Services'

    def _clean_date(self, date_str: Any) -> Optional[str]:
        """
        Parse and normalize date to ISO format (YYYY-MM-DD).
        Handles multiple common date formats.
        """
        if not date_str:
            return None

        date_str = str(date_str).strip()

        date_formats = [
            '%Y-%m-%d',
            '%d-%m-%Y',
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%Y/%m/%d',
            '%d %B %Y',
            '%d %b %Y',
            '%B %d, %Y',
            '%b %d, %Y',
            '%d-%b-%Y',
            '%d.%m.%Y',
        ]

        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        date_str_cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str_cleaned, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_str}")
        return None

    def _clean_attachments(self, attachments: Any) -> List[Dict[str, str]]:
        """Clean and validate attachment list."""
        if not isinstance(attachments, list):
            return []

        cleaned = []
        for att in attachments:
            if isinstance(att, dict) and 'url' in att:
                cleaned.append({
                    'name': self._clean_text(att.get('name')) or 'Document',
                    'url': att['url'].strip() if att['url'] else ''
                })

        return cleaned

    def _validate_required_fields(self, tender: Dict[str, Any]) -> bool:
        """Validate that all required fields are present and non-empty."""
        required_fields = [
            'tender_id',
            'title',
            'organization',
            'tender_type',
            'publish_date',
            'description',
        ]

        for field in required_fields:
            if not tender.get(field):
                logger.debug(f"Missing required field: {field}")
                return False

        if tender['tender_type'] not in self.TENDER_TYPES:
            logger.debug(f"Invalid tender_type: {tender['tender_type']}")
            return False

        return True

    def deduplicate(self, tenders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate tenders based on tender_id.
        Keeps the first occurrence.
        """
        seen = set()
        unique = []

        for tender in tenders:
            tender_id = tender.get('tender_id')
            if tender_id and tender_id not in seen:
                seen.add(tender_id)
                unique.append(tender)

        duplicates_removed = len(tenders) - len(unique)
        if duplicates_removed > 0:
            logger.info(f"Removed {duplicates_removed} duplicate tenders")

        return unique

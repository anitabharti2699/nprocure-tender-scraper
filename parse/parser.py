import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class TenderParser:
    """
    Extracts tender data from nprocure HTML responses.
    Handles both listing pages and detail pages.
    """

    def __init__(self, base_url: str = "https://tender.nprocure.com"):
        self.base_url = base_url

    def parse_listing_page(self, html: str) -> List[Dict[str, Any]]:
        """
        Extract tender listings from search/browse page.
        Returns list of tender summaries with URLs for detail pages.
        """
        soup = BeautifulSoup(html, 'html.parser')
        tenders = []

        tender_cards = soup.select('.tender-card, .tender-item, tr.tender-row')

        if not tender_cards:
            logger.warning("No tender cards found on listing page")
            return []

        for card in tender_cards:
            try:
                tender = self._extract_listing_item(card)
                if tender:
                    tenders.append(tender)
            except Exception as e:
                logger.error(f"Error parsing tender card: {e}")
                continue

        logger.info(f"Parsed {len(tenders)} tenders from listing page")
        return tenders

    def _extract_listing_item(self, card) -> Optional[Dict[str, Any]]:
        """Extract basic tender info from a listing card."""

        title_elem = card.select_one('.tender-title, .title, h3, td.title')
        link_elem = card.select_one('a[href*="tender"], a[href*="detail"]')
        org_elem = card.select_one('.organization, .org-name, .agency, td.organization')
        date_elem = card.select_one('.publish-date, .date-published, td.date')
        type_elem = card.select_one('.tender-type, .category, td.type')

        if not title_elem or not link_elem:
            return None

        tender_id = self._extract_tender_id(link_elem.get('href', ''))
        if not tender_id:
            return None

        return {
            'tender_id': tender_id,
            'title': title_elem.get_text(strip=True),
            'source_url': urljoin(self.base_url, link_elem.get('href', '')),
            'organization': org_elem.get_text(strip=True) if org_elem else None,
            'publish_date': date_elem.get_text(strip=True) if date_elem else None,
            'tender_type': type_elem.get_text(strip=True) if type_elem else None,
        }

    def parse_detail_page(self, html: str, tender_id: str) -> Optional[Dict[str, Any]]:
        """
        Extract complete tender details from detail page.
        Returns fully structured tender record.
        """
        soup = BeautifulSoup(html, 'html.parser')

        try:
            tender = {
                'tender_id': tender_id,
                'title': self._extract_title(soup),
                'organization': self._extract_organization(soup),
                'tender_type': self._extract_type(soup),
                'publish_date': self._extract_publish_date(soup),
                'closing_date': self._extract_closing_date(soup),
                'description': self._extract_description(soup),
                'attachments': self._extract_attachments(soup),
            }

            if not tender['title']:
                logger.error(f"No title found for tender {tender_id}")
                return None

            return tender

        except Exception as e:
            logger.error(f"Error parsing detail page for {tender_id}: {e}")
            return None

    def _extract_tender_id(self, url: str) -> Optional[str]:
        """Extract stable tender ID from URL."""
        if not url:
            return None

        parts = url.split('/')
        for part in reversed(parts):
            if part and part.isdigit():
                return part
            if part and any(c.isdigit() for c in part):
                cleaned = ''.join(c for c in part if c.isalnum() or c == '-')
                if cleaned:
                    return cleaned

        return None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract tender title."""
        selectors = [
            'h1.tender-title',
            '.tender-detail h1',
            'h1',
            '.page-title h1',
            '#tender-title'
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        return None

    def _extract_organization(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract procuring organization name."""
        selectors = [
            '.organization-name',
            '.agency-name',
            '.procuring-entity',
            'dt:contains("Organization") + dd',
            'label:contains("Organization") + span',
            '.tender-org'
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        return None

    def _extract_type(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract tender type (Goods/Works/Services)."""
        selectors = [
            '.tender-type',
            '.category',
            'dt:contains("Type") + dd',
            'dt:contains("Category") + dd',
            '.tender-category'
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if 'goods' in text.lower():
                    return 'Goods'
                elif 'works' in text.lower():
                    return 'Works'
                elif 'services' in text.lower():
                    return 'Services'
                return text

        return None

    def _extract_publish_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract publication date."""
        selectors = [
            '.publish-date',
            '.date-published',
            'dt:contains("Published") + dd',
            'dt:contains("Posted") + dd',
            '.tender-publish-date'
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        return None

    def _extract_closing_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract closing/deadline date."""
        selectors = [
            '.closing-date',
            '.deadline',
            'dt:contains("Closing") + dd',
            'dt:contains("Deadline") + dd',
            '.tender-closing-date'
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        return None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract tender description."""
        selectors = [
            '.tender-description',
            '.description',
            '#description',
            'dt:contains("Description") + dd',
            '.tender-detail-description',
            '.tender-details .content'
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(separator=' ', strip=True)

        return None

    def _extract_attachments(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract document attachments."""
        attachments = []

        attachment_sections = soup.select('.attachments, .documents, #attachments')

        for section in attachment_sections:
            links = section.select('a[href]')
            for link in links:
                href = link.get('href', '')
                if any(ext in href.lower() for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']):
                    attachments.append({
                        'name': link.get_text(strip=True) or 'Document',
                        'url': urljoin(self.base_url, href)
                    })

        if not attachment_sections:
            all_links = soup.select('a[href*=".pdf"], a[href*=".doc"]')
            for link in all_links[:10]:
                href = link.get('href', '')
                attachments.append({
                    'name': link.get_text(strip=True) or 'Document',
                    'url': urljoin(self.base_url, href)
                })

        return attachments

    def get_pagination_info(self, html: str) -> Dict[str, Any]:
        """Extract pagination information from listing page."""
        soup = BeautifulSoup(html, 'html.parser')

        pagination = {
            'current_page': 1,
            'total_pages': 1,
            'has_next': False,
            'next_url': None
        }

        current_elem = soup.select_one('.pagination .active, .current-page')
        if current_elem:
            try:
                pagination['current_page'] = int(current_elem.get_text(strip=True))
            except ValueError:
                pass

        next_link = soup.select_one('.pagination a:contains("Next"), a.next-page, a[rel="next"]')
        if next_link and next_link.get('href'):
            pagination['has_next'] = True
            pagination['next_url'] = urljoin(self.base_url, next_link.get('href'))

        page_links = soup.select('.pagination a[href]')
        if page_links:
            try:
                pages = [int(link.get_text(strip=True)) for link in page_links if link.get_text(strip=True).isdigit()]
                if pages:
                    pagination['total_pages'] = max(pages)
            except ValueError:
                pass

        return pagination

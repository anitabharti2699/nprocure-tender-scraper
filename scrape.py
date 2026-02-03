#!/usr/bin/env python3
"""
nprocure Tender Scraper

Production-grade web scraper for https://tender.nprocure.com/
Extracts tender data and persists to Supabase with full observability.
"""

import os
import sys
import argparse
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv

from fetch import Fetcher
from parse import TenderParser
from clean import DataCleaner
from store import TenderStorage
from metadata import RunTracker

VERSION = "1.0.0"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class TenderScraper:
    """
    Main scraper orchestrator.
    Coordinates fetching, parsing, cleaning, and storage.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

        self.fetcher = Fetcher(
            rate_limit=config['rate_limit'],
            timeout=config['timeout'],
            max_retries=config['retries'],
            base_url=config['base_url']
        )
        self.parser = TenderParser(base_url=config['base_url'])
        self.cleaner = DataCleaner()
        self.storage = TenderStorage()
        self.tracker = RunTracker(config=config, version=VERSION)

    def run(self):
        """Execute the scraping process."""
        logger.info("Starting nprocure tender scraper")
        self.tracker.start_run()

        try:
            tenders = self._scrape_tenders()

            if not tenders:
                logger.warning("No tenders found")
                self.tracker.complete_run(status='completed')
                return

            cleaned_tenders = self._clean_tenders(tenders)

            if not cleaned_tenders:
                logger.warning("No valid tenders after cleaning")
                self.tracker.complete_run(status='completed')
                return

            self._save_tenders(cleaned_tenders)

            self.tracker.complete_run(status='completed')

            logger.info(
                f"Scraping completed: {self.tracker.tenders_saved} tenders saved, "
                f"{self.tracker.deduped_count} duplicates skipped"
            )

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            self.tracker.complete_run(status='failed')
            sys.exit(1)

        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            self.tracker.record_error('fatal_error')
            self.tracker.complete_run(status='failed')
            sys.exit(1)

        finally:
            self.fetcher.close()

    def _scrape_tenders(self) -> List[Dict[str, Any]]:
        """Scrape tenders from listing and detail pages."""
        all_tenders = []
        page = 1
        max_pages = self.config.get('max_pages', 10)

        while page <= max_pages:
            logger.info(f"Fetching page {page}")

            listing_url = f"/?page={page}" if page > 1 else "/"
            response = self.fetcher.get(listing_url)

            if response is None:
                logger.error(f"Failed to fetch page {page}")
                self.tracker.record_error('fetch_error')
                break

            self.tracker.increment_pages()

            tender_list = self.parser.parse_listing_page(response.text)

            if not tender_list:
                logger.info(f"No tenders found on page {page}, stopping")
                break

            logger.info(f"Found {len(tender_list)} tenders on page {page}")

            for tender_summary in tender_list:
                tender_detail = self._fetch_tender_detail(tender_summary)
                if tender_detail:
                    all_tenders.append(tender_detail)

                if self.config.get('limit') and len(all_tenders) >= self.config['limit']:
                    logger.info(f"Reached limit of {self.config['limit']} tenders")
                    return all_tenders

            pagination = self.parser.get_pagination_info(response.text)
            if not pagination['has_next']:
                logger.info("No more pages available")
                break

            page += 1

        return all_tenders

    def _fetch_tender_detail(self, tender_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch and parse a single tender detail page."""
        tender_id = tender_summary['tender_id']
        source_url = tender_summary['source_url']

        logger.debug(f"Fetching tender {tender_id}")

        response = self.fetcher.get(source_url)

        if response is None:
            logger.warning(f"Failed to fetch tender {tender_id}")
            self.tracker.record_error('detail_fetch_error')
            return None

        self.tracker.increment_pages()

        tender_detail = self.parser.parse_detail_page(response.text, tender_id)

        if tender_detail is None:
            logger.warning(f"Failed to parse tender {tender_id}")
            self.tracker.record_error('parse_error')
            return None

        tender_detail['source_url'] = source_url

        for key, value in tender_summary.items():
            if key not in tender_detail or not tender_detail[key]:
                tender_detail[key] = value

        self.tracker.increment_parsed()
        return tender_detail

    def _clean_tenders(self, tenders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clean and validate tender data."""
        logger.info(f"Cleaning {len(tenders)} tenders")

        cleaned = []
        for tender in tenders:
            clean_tender = self.cleaner.clean_tender(tender)
            if clean_tender:
                cleaned.append(clean_tender)
            else:
                self.tracker.record_error('validation_error')

        logger.info(f"{len(cleaned)} tenders passed validation")
        return cleaned

    def _save_tenders(self, tenders: List[Dict[str, Any]]):
        """Save tenders to database."""
        logger.info(f"Saving {len(tenders)} tenders to database")

        stats = self.storage.save_tenders_batch(tenders)

        self.tracker.update_stats({
            'saved': stats['saved'],
            'deduped': stats['deduped'],
            'failed': stats['failed']
        })

        logger.info(
            f"Saved {stats['saved']} tenders, "
            f"skipped {stats['deduped']} duplicates, "
            f"{stats['failed']} failures"
        )


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Scrape tenders from nprocure.com',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--rate-limit',
        type=float,
        default=1.0,
        help='Requests per second (default: 1.0)'
    )

    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Request timeout in seconds (default: 30)'
    )

    parser.add_argument(
        '--retries',
        type=int,
        default=3,
        help='Max retries per request (default: 3)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Maximum number of tenders to scrape (default: no limit)'
    )

    parser.add_argument(
        '--max-pages',
        type=int,
        default=10,
        help='Maximum number of listing pages to scrape (default: 10)'
    )

    parser.add_argument(
        '--base-url',
        type=str,
        default='https://tender.nprocure.com',
        help='Base URL of tender site (default: https://tender.nprocure.com)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    load_dotenv()

    if not os.getenv('SUPABASE_URL') or not os.getenv('SUPABASE_ANON_KEY'):
        logger.error("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env file")
        sys.exit(1)

    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = {
        'rate_limit': args.rate_limit,
        'timeout': args.timeout,
        'retries': args.retries,
        'limit': args.limit,
        'max_pages': args.max_pages,
        'base_url': args.base_url,
    }

    scraper = TenderScraper(config)
    scraper.run()


if __name__ == '__main__':
    main()

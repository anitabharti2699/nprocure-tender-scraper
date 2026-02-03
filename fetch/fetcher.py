import time
import logging
from typing import Optional, Dict, Any
from urllib.parse import urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class Fetcher:
    """
    HTTP client with retry logic, rate limiting, and timeout handling.
    Designed for reliable data collection from tender portals.
    """

    def __init__(
        self,
        rate_limit: float = 1.0,
        timeout: int = 30,
        max_retries: int = 3,
        base_url: str = "https://tender.nprocure.com"
    ):
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = base_url
        self.last_request_time = 0

        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry strategy and realistic headers."""
        session = requests.Session()

        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

        return session

    def _enforce_rate_limit(self):
        """Enforce rate limiting between requests."""
        if self.rate_limit > 0:
            elapsed = time.time() - self.last_request_time
            wait_time = (1.0 / self.rate_limit) - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
        self.last_request_time = time.time()

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[requests.Response]:
        """
        Fetch URL with rate limiting and error handling.
        Returns None on failure after retries.
        """
        self._enforce_rate_limit()

        full_url = urljoin(self.base_url, url) if not url.startswith('http') else url

        try:
            response = self.session.get(
                full_url,
                params=params,
                timeout=self.timeout,
                allow_redirects=True
            )
            response.raise_for_status()
            logger.debug(f"Successfully fetched {full_url}")
            return response

        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching {full_url}")
            return None

        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error fetching {full_url}")
            return None

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code} fetching {full_url}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error fetching {full_url}: {e}")
            return None

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Fetch and parse JSON response."""
        response = self.get(url, params)
        if response is None:
            return None

        try:
            return response.json()
        except ValueError:
            logger.error(f"Invalid JSON response from {url}")
            return None

    def close(self):
        """Close the session."""
        self.session.close()

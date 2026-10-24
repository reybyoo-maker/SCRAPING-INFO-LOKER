import hashlib
import unittest

import yaml

from scripts.run_all import deduplicate, normalize_record
from scrapers import SCRAPER_CLASSES, BaseScraper


class OrchestratorSchemaTests(unittest.TestCase):
    def test_normalizes_to_common_schema_and_preserves_site_aliases(self):
        source = {
            "id": "old-collector-id",
            "title": "Staff Administrasi",
            "company_name": "PT Contoh",
            "city": "Bandung",
            "province": "Jawa Barat",
            "source_name": "Google News RSS",
            "listing_url": "https://example.com/jobs/123",
            "published_at": "2026-10-24T08:00:00Z",
            "salary_text": "Rp4.000.000",
            "employment_type": "Full-time",
            "description_excerpt": "Pekerjaan administrasi kantor.",
            "last_seen_at": "2026-10-25T00:00:00Z",
        }
        row = normalize_record(source)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], hashlib.sha256(
            "https://example.com/jobs/123Staff AdministrasiPT Contoh".encode("utf-8")
        ).hexdigest()[:16])
        self.assertEqual(row["source"], "google_news_rss")
        self.assertEqual(row["job_type"], "fulltime")
        self.assertEqual(row["location"], "Bandung, Jawa Barat")
        self.assertLessEqual(len(row["description_snippet"]), 300)
        self.assertEqual(row["listing_url"], row["url"])
        self.assertEqual(row["collector_id"], "old-collector-id")

    def test_deduplicates_equal_url_title_company(self):
        row = {
            "title": "Customer Service",
            "company_name": "PT Contoh",
            "source_name": "Google News RSS",
            "listing_url": "https://example.com/jobs/abc",
            "last_seen_at": "2026-10-25T00:00:00Z",
        }
        result = deduplicate([row, dict(row, salary_text="Rp5.000.000")])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["salary"], "Rp5.000.000")

    def test_all_eleven_adapters_inherit_base_scraper(self):
        self.assertEqual(len(SCRAPER_CLASSES), 11)
        self.assertTrue(all(issubclass(adapter, BaseScraper) for adapter in SCRAPER_CLASSES))

    def test_source_adapters_are_disabled_by_default(self):
        config = yaml.safe_load(open("config.yaml", encoding="utf-8"))
        self.assertEqual(len(config["sources"]), 11)
        self.assertTrue(all(item["enabled"] is False for item in config["sources"].values()))
        self.assertTrue(all(item["authorized"] is False for item in config["sources"].values()))


if __name__ == "__main__":
    unittest.main()

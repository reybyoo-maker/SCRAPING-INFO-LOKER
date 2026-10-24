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

    def test_dealls_parser_extracts_public_loker_cards(self):
        from scrapers.dealls import DeallsScraper

        settings = {
            "enabled": True,
            "authorized": True,
            "search_url": "https://dealls.com/loker",
        }
        scraper = DeallsScraper(settings, keyword="lowongan kerja", location="Indonesia")
        html = """
        <html><body><main>
          <a href="/loker/content-creator-and-live-host~pt-jaya-mulia-permata">
            <article>
              <h2>Content Creator &amp; Live Host</h2>
              <span class="company-name">PT Jaya Mulia Permata</span>
              <span class="location">On-site • Jakarta Timur</span>
              <span class="salary">Rp4.000.000 – 5.000.000</span>
              <span>Penuh waktu</span>
            </article>
          </a>
        </main></body></html>
        """
        rows = scraper.parse(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Content Creator & Live Host")
        self.assertEqual(rows[0]["source"], "dealls")
        self.assertEqual(rows[0]["salary"], "Rp4.000.000 – 5.000.000")
        self.assertEqual(rows[0]["url"], "https://dealls.com/loker/content-creator-and-live-host~pt-jaya-mulia-permata")

    def test_only_robots_gated_public_html_adapters_are_enabled(self):
        config = yaml.safe_load(open("config.yaml", encoding="utf-8"))
        sources = config["sources"]
        self.assertEqual(len(sources), 11)
        enabled = {name for name, item in sources.items() if item.get("enabled") is True}
        self.assertEqual(enabled, {"kalibrr", "dealls", "techinasia", "maganghub"})
        self.assertTrue(all(sources[name]["authorized"] is True for name in enabled))
        for name in ("jobstreet", "indeed", "glints", "karir", "linkedin", "lokerid", "disnakerja"):
            self.assertIs(sources[name]["enabled"], False, f"{name} must remain permission-gated")
            self.assertIs(sources[name]["authorized"], False, f"{name} must remain permission-gated")
        self.assertIs(sources["linkedin"]["enabled"], False)


if __name__ == "__main__":
    unittest.main()

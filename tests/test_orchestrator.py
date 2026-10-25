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

    def test_filters_navigation_cta_titles_without_rejecting_real_job_titles(self):
        for title in ("English", "Apply", "Sign up", "See More", "Lamar sekarang",
                      "Lompat ke konten utama", "Academics", "Pendaftaran"):
            self.assertIsNone(normalize_record({
                "title": title,
                "company_name": "Example Indonesia",
                "listing_url": f"https://example.com/careers/jobs/{title.lower().replace(' ', '-')}",
            }), f"CTA should not be treated as a vacancy: {title}")

        self.assertIsNotNone(normalize_record({
            "title": "Crew Outlet (PaintPro)",
            "company_name": "Brik",
            "listing_url": "https://example.com/careers/jobs/crew-outlet",
        }))

    def test_deduplicates_canonical_url_tracking_variants_and_preserves_source_key(self):
        first = {
            "id": "legacy-record-1",
            "title": "Staff Support",
            "company_name": "Example Indonesia",
            "source_name": "Example Careers",
            "listing_url": "https://www.example.com/jobs/abc?utm_source=feed#apply",
            "last_seen_at": "2026-10-25T00:00:00Z",
        }
        second = {
            "id": "legacy-record-2",
            "title": "Staff Support",
            "company_name": "Example Indonesia",
            "source_name": "Example Careers",
            "listing_url": "https://example.com/jobs/abc",
            "salary_text": "Rp5.000.000",
            "last_seen_at": "2026-10-25T01:00:00Z",
        }
        result = deduplicate([first, second])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["collector_id"], "legacy-record-1")
        self.assertEqual(result[0]["salary"], "Rp5.000.000")
        self.assertEqual(result[0]["title"], "Staff Support")

    def test_keeps_distinct_postings_that_share_a_career_landing_url(self):
        shared_url = "https://example.com/careers"
        records = [
            {
                "title": "Network Engineer",
                "company_name": "Example Indonesia",
                "listing_url": shared_url,
                "source_name": "Example Careers",
            },
            {
                "title": "Network Analyst",
                "company_name": "Example Indonesia",
                "listing_url": shared_url,
                "source_name": "Example Careers",
            },
        ]
        result = deduplicate(records)
        self.assertEqual(len(result), 2)
        self.assertEqual({row["title"] for row in result}, {"Network Engineer", "Network Analyst"})

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

    def test_only_safe_source_adapters_are_enabled(self):
        config = yaml.safe_load(open("config.yaml", encoding="utf-8"))
        sources = config["sources"]
        self.assertEqual(len(sources), 11)
        enabled = {name for name, item in sources.items() if item.get("enabled") is True}
        self.assertEqual(enabled, {"kalibrr", "dealls", "maganghub"})
        self.assertTrue(all(sources[name]["authorized"] is True for name in enabled))
        for name in ("jobstreet", "indeed", "glints", "karir", "linkedin", "lokerid", "disnakerja", "techinasia"):
            self.assertIs(sources[name]["enabled"], False, f"{name} must remain inactive")
            self.assertIs(sources[name]["authorized"], False, f"{name} must remain inactive")
        self.assertEqual(sources["maganghub"]["min_delay_seconds"], 5)
        self.assertEqual(sources["maganghub"]["max_delay_seconds"], 10)
        self.assertFalse(sources["linkedin"]["enabled"])

    def test_maganghub_uses_indonesian_language_and_explicit_bot_identity(self):
        from scrapers.maganghub import MaganghubScraper

        settings = yaml.safe_load(open("config.yaml", encoding="utf-8"))["sources"]["maganghub"]
        scraper = MaganghubScraper(settings, keyword="magang", location="Indonesia")
        self.assertIn("INFOLOKERIndonesiaBot", scraper.session.headers["User-Agent"])
        self.assertTrue(scraper.session.headers["Accept-Language"].startswith("id-ID"))
        self.assertEqual(scraper.min_delay_seconds, 5)
        self.assertEqual(scraper.max_delay_seconds, 10)

    def test_karir_api_adapter_parses_sample_json_without_live_requests(self):
        import json
        from scrapers.karir import KarirScraper

        scraper = KarirScraper({"enabled": False, "authorized": False,
                                "search_url": "https://karir-ms-beta.karir.com/v2/search/opportunities"})
        payload = {
            "data": {
                "opportunities": [{
                    "title": "Backend Engineer",
                    "company": {"name": "PT Contoh"},
                    "location": {"city": "Bandung"},
                    "url": "/jobs/backend-engineer",
                    "published_at": "2026-10-20T08:00:00Z",
                    "salary": "Rp8.000.000",
                    "description": "Build backend services."
                }]
            }
        }
        rows = scraper.parse(json.dumps(payload))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Backend Engineer")
        self.assertEqual(rows[0]["company"], "PT Contoh")
        self.assertEqual(rows[0]["location"], "Bandung")
        self.assertEqual(rows[0]["url"], "https://www.karir.com/jobs/backend-engineer")
        self.assertEqual(rows[0]["source_type"], "permission_gated_json_api")

    def test_karir_api_adapter_cannot_fetch_without_authorization(self):
        from scrapers.karir import KarirScraper
        from scrapers.base import SourceNotAllowed

        scraper = KarirScraper({"enabled": True, "authorized": False,
                                "search_url": "https://karir-ms-beta.karir.com/v2/search/opportunities"})
        with self.assertRaises(SourceNotAllowed):
            scraper.fetch()


if __name__ == "__main__":
    unittest.main()

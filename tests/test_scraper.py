import unittest
from datetime import datetime, timedelta, timezone
from scraper.main import (
    clean_position, extract_education, extract_phone, extract_salary,
    infer_job_category, match_location, quality, query_pool, safe_public_url,
    select_query_batch
)


class ScraperHelpersTest(unittest.TestCase):
    def test_three_daily_runs_cover_all_configured_areas(self):
        pool = query_pool()
        expected = {item["q"] for item in pool if item.get("priority") == "geo"}
        base = datetime(2026, 10, 25, 0, 15, tzinfo=timezone.utc)
        selected_geo = []
        for run_offset in (0, 8, 16):
            batch, stats = select_query_batch(pool, 120, base + timedelta(hours=run_offset))
            self.assertEqual(len(batch), 120)
            expected_geo_per_run = min(120, (len(expected) + 2) // 3)
            self.assertEqual(stats["selected_geo_queries"], expected_geo_per_run)
            selected_geo.extend(item["q"] for item in batch if item.get("priority") == "geo")
        self.assertEqual(set(selected_geo), expected)
        self.assertEqual(len(selected_geo), len(expected))

    def test_position_cleanup(self):
        self.assertEqual(
            clean_position("Lowongan Kerja Staff Admin - PT Contoh Indonesia"),
            "Staff Admin - PT Contoh Indonesia",
        )

    def test_job_category_inference(self):
        self.assertEqual(infer_job_category("Customer Service Representative"), "Customer Service")
        self.assertEqual(infer_job_category("Operator Produksi Pabrik"), "Operations & Logistics")
        self.assertEqual(infer_job_category("UI/UX Designer"), "Design & Creative")

    def test_salary_range(self):
        text, minimum, maximum = extract_salary("Gaji Rp 4.000.000 - Rp 6.000.000 per bulan")
        self.assertIsNotNone(text)
        self.assertEqual(minimum, 4_000_000)
        self.assertEqual(maximum, 6_000_000)

    def test_education_detection(self):
        self.assertEqual(extract_education("Persyaratan: minimal pendidikan SMA/SMK"), "SMA/SMK sederajat")

    def test_phone_detection(self):
        self.assertEqual(extract_phone("Hubungi 0812-3456-7890"), "081234567890")

    def test_public_url_validation(self):
        self.assertTrue(safe_public_url("https://example.com/jobs"))
        self.assertFalse(safe_public_url("http://127.0.0.1/admin"))
        self.assertFalse(safe_public_url("file:///etc/passwd"))

    def test_city_mapping(self):
        city, province, confidence = match_location("Dibuka loker Staff Admin area Bandung, Jawa Barat")
        self.assertEqual(city, "Bandung")
        self.assertEqual(province, "Jawa Barat")
        self.assertEqual(confidence, "matched_in_listing")

    def test_explicit_unknown_city_is_not_replaced_by_search_hint(self):
        title = "PT Arwana Citramulia Buka Lowongan Kerja di Pamekasan, Simak Syarat"
        city, province, confidence = match_location(
            title,
            {"city": "Karawang", "province": "Jawa Barat"},
        )
        self.assertIsNone(city)
        self.assertIsNone(province)
        self.assertEqual(confidence, "unresolved_location_in_text")

    def test_explicit_known_city_beats_search_hint(self):
        title = "Lowongan Kerja di Gresik, Jawa Timur"
        city, province, confidence = match_location(
            title,
            {"city": "Karawang", "province": "Jawa Barat"},
        )
        self.assertEqual(city, "Gresik")
        self.assertEqual(province, "Jawa Timur")
        self.assertEqual(confidence, "matched_in_listing")

    def test_quality_handles_missing_description(self):
        sample = {
            "source_type": "rss_search",
            "title": "Lowongan Staff",
            "description_excerpt": None,
            "requirements": None,
            "risk_flags": [],
            "published_at": None,
            "source_updated_at": None,
        }
        score, label, reasons = quality(sample)
        self.assertEqual(label, "LOW")
        self.assertGreaterEqual(score, 0)

    def test_quality_hot_is_not_a_legitimacy_claim(self):
        sample = {
            "source_type": "public_api",
            "title": "Customer Support",
            "company_name": "Contoh PT",
            "listing_url": "https://example.com/jobs/1",
            "application_url": "https://example.com/jobs/1",
            "city": "Bandung",
            "province": "Jawa Barat",
            "location_confidence": "matched_in_listing",
            "salary_text": "Rp 5.000.000",
            "education_minimum": "SMA/SMK",
            "description_excerpt": "Lowongan customer support",
            "published_at": "2099-01-01T00:00:00Z",
            "source_updated_at": "2099-01-01T00:00:00Z",
            "risk_flags": [],
        }
        score, label, reasons = quality(sample)
        self.assertEqual(label, "HOT")
        self.assertGreaterEqual(score, 75)
        self.assertTrue(any("verifikasi" in item.lower() for item in reasons))


if __name__ == "__main__":
    unittest.main()

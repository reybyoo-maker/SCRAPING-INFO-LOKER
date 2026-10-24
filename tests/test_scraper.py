import unittest
from scraper.main import (
    clean_position, extract_education, extract_phone, extract_salary,
    match_location, quality, safe_public_url
)


class ScraperHelpersTest(unittest.TestCase):
    def test_position_cleanup(self):
        self.assertEqual(
            clean_position("Lowongan Kerja Staff Admin - PT Contoh Indonesia"),
            "Staff Admin - PT Contoh Indonesia",
        )

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

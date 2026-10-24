import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from scrapers.company_sites.base_company import (
    BlockedDomainRegistry,
    CompanySiteClient,
    RobotsDisallowed,
    RATE_LIMITER,
)
from scrapers.company_sites.generic_parser import GenericCompanyParser
from scrapers.company_sites import load_targets
from scripts.run_all import normalize_record
from scrapers.company_sites.specific import SPECIFIC_PARSERS
from scrapers.company_sites.categories import CATEGORY_PARSERS


class CompanyTargetConfigTests(unittest.TestCase):
    def test_curated_company_targets_has_200_plus_real_records(self):
        config, targets = load_targets()
        raw = yaml.safe_load(Path("config/company_targets.yaml").read_text(encoding="utf-8"))["targets"]
        self.assertGreaterEqual(len(raw), 200)
        self.assertGreaterEqual(len(targets), 200)
        self.assertEqual(config["run_every_hours"], 6)
        self.assertLessEqual(config["max_workers"], 8)
        self.assertLessEqual(config["max_requests_per_domain_per_run"], 50)
        self.assertTrue(all(t.get("domain") and t.get("website", "").startswith("https://") for t in targets))
        categories = {t.get("category") for t in targets}
        for value in ("BUMN", "Startup", "Corporate", "Manufaktur", "Fintech", "Healthcare"):
            self.assertIn(value, categories)

    def test_twenty_specific_parsers_are_registered(self):
        self.assertGreaterEqual(len(SPECIFIC_PARSERS), 20)
        self.assertGreaterEqual(len(CATEGORY_PARSERS), 13)

    def test_company_job_schema_and_source_namespace(self):
        target = {
            "id": "bca",
            "name": "Bank Example",
            "domain": "examplebank.co.id",
            "category": "Fintech",
        }
        html = """
        <html><body><main><ul>
          <li class="job-listing">
            <h3><a href="/careers/jobs/senior-data-engineer">Senior Data Engineer</a></h3>
            <span class="location">Jakarta, Indonesia</span>
            <span class="salary">Rp10.000.000</span>
            <span class="employment">Full-time</span>
            <p>Build the data platform and APIs.</p>
          </li>
        </ul></main></body></html>
        """
        rows = GenericCompanyParser(target).parse(html, "https://examplebank.co.id/careers")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        for key in ("id", "title", "company", "location", "source", "url",
                    "posted_at", "salary", "job_type", "description_snippet", "scraped_at"):
            self.assertIn(key, row)
        self.assertEqual(row["company"], "Bank Example")
        self.assertEqual(row["source"], "company:examplebank.co.id")
        self.assertEqual(row["category"], "Fintech")
        self.assertEqual(row["source_group"], "Company Sites")
        self.assertEqual(row["url"], "https://examplebank.co.id/careers/jobs/senior-data-engineer")
        normalized = normalize_record(row)
        self.assertEqual(normalized["source"], "company:examplebank.co.id")
        self.assertEqual(normalized["category"], "Fintech")
        self.assertEqual(normalized["source_group"], "Company Sites")

    def test_persisted_blocklist_prevents_domain_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "blocked_domains.json"
            registry = BlockedDomainRegistry(path)
            registry.add("https://jobs.example.org/careers", "HTTP 403", 403)
            reloaded = BlockedDomainRegistry(path)
            self.assertTrue(reloaded.is_blocked("jobs.example.org"))
            self.assertEqual(reloaded.entries["jobs.example.org"]["http_status"], 403)
            client = CompanySiteClient(
                {"name": "Example", "domain": "jobs.example.org", "website": "https://jobs.example.org/"},
                blocked_registry=reloaded,
            )
            with self.assertRaises(Exception):
                client.get("https://jobs.example.org/careers")

    def test_robots_disallow_means_no_career_page_request(self):
        target = {"name": "Example", "domain": "example.org", "website": "https://example.org/"}
        with tempfile.TemporaryDirectory() as temp:
            client = CompanySiteClient(target, blocked_registry=BlockedDomainRegistry(Path(temp) / "blocked.json"))
            response = Mock(status_code=200, text="User-agent: *\nDisallow: /careers\n", headers={})
            with patch.object(client, "_send", return_value=response) as send:
                with self.assertRaises(RobotsDisallowed):
                    client.get("https://example.org/careers")
                self.assertEqual(send.call_count, 1)


if __name__ == "__main__":
    unittest.main()

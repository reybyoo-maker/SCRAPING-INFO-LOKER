# Website integration notes

The collector's website-ready dataset lives at:

https://raw.githubusercontent.com/reybyoo-maker/SCRAPING-INFO-LOKER/main/data/jobs.json

Top-level shape:

- schema_version: feed schema version
- generated_at: last successful generation time in UTC
- timezone: the intended display timezone, Asia/Jakarta
- total: number of retained records
- fresh_seen_in_this_run: records collected in this run before deduplication
- jobs: normalized job records

## Recommended filters

- Province and city: province, city
- Position/category: position or title
- Freshness: source_updated_at, published_at, last_seen_at
- Education: education_minimum
- Salary: salary_min_idr, salary_max_idr, salary_text
- Work arrangement: work_mode
- Employment: employment_type
- Walk-in: walk_in, walk_in_date, walk_in_location
- Informational quality: quality_label and quality_score
- State: listing_state (active_unverified, stale, deadline_passed)

## Important display behavior

1. Make source_updated_at and last_seen_at visually distinct. The first is the date the publisher/API says it updated the listing; the second is when this collector last encountered it.
2. Do not render an empty salary as Rp 0. Display “Gaji tidak dicantumkan”.
3. Treat location_confidence=search_context as an inferred filter hint, not a confirmed workplace. Display a subtle “lokasi dari konteks pencarian” label.
4. HOT/MEDIUM/LOW reflects freshness, completeness and source signals. It does not certify that a company or vacancy is legitimate. Keep the source link prominent.
5. Use the original listing_url/application_url to let applicants verify the vacancy. Do not copy full vacancy text or download/re-host original flyers.
6. The feed can be stale when GitHub Actions is paused, a source is rate-limited, or a provider removes items. Check data/run_status.json and show the last data refresh time.
7. For production, migrate the data into a database and serve it from an API instead of using Git history as a database. Use official APIs or written permission for job boards and social platforms that restrict automated collection.

## Example filter function

    export function filterJobs(jobs, filters) {
      return jobs.filter((job) => {
        if (filters.province && job.province !== filters.province) return false;
        if (filters.city && job.city !== filters.city) return false;
        if (filters.education && job.education_minimum !== filters.education) return false;
        if (filters.workMode && job.work_mode !== filters.workMode) return false;
        if (filters.walkIn === true && job.walk_in !== true) return false;
        if (filters.quality && job.quality_label !== filters.quality) return false;
        if (filters.salaryOnly && !job.salary_text) return false;
        if (filters.query) {
          const searchable = [job.title, job.position, job.company_name, job.description_excerpt]
            .filter(Boolean).join(" ").toLowerCase();
          if (!searchable.includes(filters.query.toLowerCase())) return false;
        }
        return true;
      });
    }

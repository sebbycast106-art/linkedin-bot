# LinkedIn Bot: Profile Enrichment + Recruiter Outreach Design

**Date:** 2026-03-28

**Goal:** Enrich connector outreach with real profile data, auto-log scraped jobs into the application tracker, and add a two-phase recruiter outreach pipeline (connect → follow-up after accept).

**Architecture:** Option B — new files per concern. `profile_scraper.py` handles profile data extraction. `recruiter_service.py` handles recruiter discovery, connection, and follow-up. Existing services call these new modules rather than inlining logic.

**Tech Stack:** Playwright (existing), Flask (existing), AI service (existing), database.py state files (existing), cron-job.org (existing)

---

## New Files

### `profile_scraper.py`

Single public function: `scrape_profile(page, url) -> dict`

- Navigates to the LinkedIn profile URL
- Extracts: `headline`, `company`, `school`, `location`, `mutual_count`
- All fields optional — returns empty dict on any failure, never raises
- Caller (connector_service) continues with partial data if scraping fails
- Uses CSS selectors matching LinkedIn's current profile layout

### `recruiter_service.py`

**State file:** `recruiter_state.json`
```json
{
  "date": "2026-03-28",
  "sent_today": 3,
  "pending_followup": [
    {"profile_id": "john-smith-123", "name": "John", "company": "Fidelity", "sent_at": 1711670400}
  ],
  "messaged_ids": ["john-smith-123"]
}
```

**Daily limit:** 10 recruiter connection requests/day (separate from connector_service's 20/day limit)

**Target companies:**
Fidelity, BlackRock, Goldman Sachs, JP Morgan, Citadel, Point72, Jane Street, Robinhood, Stripe, Sequoia, General Catalyst, plus "fintech startup" and "asset management" generic searches.

**Search query pattern:**
- Keywords: `"recruiter [company]"` or `"talent acquisition [company]"`
- Network filter: 2nd-degree only (`network=S`)
- People search: `/search/results/people/`

**Public interface:**
- `find_recruiters(session) -> list[dict]` — searches all target companies, returns profiles not yet in `pending_followup` or `messaged_ids`
- `send_recruiter_connections(session) -> int` — sends personalized connection notes to found recruiters up to daily limit, adds each to `pending_followup`
- `check_and_followup(session) -> int` — iterates `pending_followup` entries older than 24hrs, visits profile, if "Message" button visible (accepted), sends follow-up message and moves to `messaged_ids`
- `run_recruiter_outreach(session) -> dict` — calls `find_recruiters` + `send_recruiter_connections`, returns `{sent: N}`
- `run_followup_check(session) -> dict` — calls `check_and_followup`, returns `{messaged: N}`

**Connection note template (AI-generated):**
Short, specific, references their company and a real detail from their profile. Max 300 chars (LinkedIn limit).

**Follow-up message template (AI-generated):**
Sent after they accept. References the connection note, mentions co-op/internship interest, asks if they have any open roles or advice. Conversational, not spammy.

---

## Modified Files

### `connector_service.py`

Before generating each connection message:
1. Get the profile URL from the search result link element
2. Call `profile_scraper.scrape_profile(page, profile_url)`
3. Pass enriched fields to `ai_service.generate_connection_message(name, role, company, school=school, headline=headline)`
4. If profile scrape fails/times out, fall back to existing behavior (name + role + company from search result)
5. Add ~3–5s random delay after profile visit before returning to search results

`ai_service.generate_connection_message` signature updated to accept optional `school` and `headline` kwargs.

### `application_tracker.py`

Add `"seen"` as a valid status alongside `applied/responded/interview/offer/rejected`.

`"seen"` means: job was scraped and logged, not yet applied. Distinct from `"applied"` so follow-up reminders don't fire for unseen jobs.

`check_follow_ups()` only triggers for `"applied"` status (unchanged behavior).

### `app.py`

**`_run_job_scraper` update:**
After getting new jobs list, call `add_application(job_id, company, title, url, status="seen")` for each. Telegram message unchanged.

**Two new endpoints:**
- `POST /internal/run-recruiter` — validates secret, runs `run_recruiter_outreach` in background thread, sends Telegram with result
- `POST /internal/run-recruiter-followup` — validates secret, runs `run_followup_check` in background thread, sends Telegram with result

---

## Cron Jobs (cron-job.org)

| Job | Schedule | Endpoint |
|-----|----------|----------|
| Recruiter Outreach | Mon/Wed/Fri 10:30AM ET | `POST /internal/run-recruiter` |
| Recruiter Follow-up | Daily 1:00PM ET | `POST /internal/run-recruiter-followup` |

---

## Error Handling

- All Playwright interactions wrapped in try/except — individual failures skip to next item
- Each service sends Telegram alert on unhandled exception (matches existing pattern)
- Profile scraper never raises — returns `{}` on any error
- Recruiter state file always reloaded before and saved after each run

---

## Testing

- `tests/test_profile_scraper.py` — unit tests with mocked Playwright page
- `tests/test_recruiter_service.py` — unit tests for state management, daily limit logic, follow-up eligibility (24hr check), deduplication
- `tests/test_app.py` — add tests for `/internal/run-recruiter` and `/internal/run-recruiter-followup` endpoints

# LinkedIn Bot — Agent Briefing

## What This Is

A LinkedIn automation bot running on Railway (Flask + Playwright + Claude AI). It runs headlessly in the cloud and is triggered by cron-job.org on a schedule. All results are sent to the user via Telegram.

**Deployed URL:** `https://linkedin-bot-production-c351.up.railway.app`
**GitHub repo:** `sebbycast106-art/linkedin-bot` (branch: `master`)
**Railway project ID:** `6c86be71-80b2-4204-9552-b6c17ffb93cb`
**Railway service ID:** `c740ddac-a04b-4f5c-b038-7a52eed6f88c`
**SCHEDULER_SECRET:** see Railway environment variables (do not commit here)

## What It Does (All Features)

| Service | File | What it does |
|---------|------|-------------|
| Job Scraper | `job_scraper.py` | Scrapes LinkedIn for new co-op/internship postings |
| Job Scorer | `job_scorer.py` | Scores jobs 1-10 with Claude Haiku; filters below 6 |
| Smart Apply Filter | `job_scorer.py` | Scores full job description (scrape + score) before Easy Apply; skips if <7 |
| Easy Apply | `easy_apply_service.py` | Submits LinkedIn Easy Apply forms; AI-generates cover letters instead of skipping |
| Connector | `connector_service.py` | Sends connection requests with AI-personalized notes (20/day) |
| Profile Enrichment | `profile_scraper.py` | Scrapes profile data (headline, school) before each connection |
| Alumni Connector | `alumni_connector_service.py` | Targets NEU alumni at finance firms specifically (10/day) |
| Engagement | `engagement_service.py` | Likes and comments on feed posts |
| Recruiter Outreach | `recruiter_service.py` | Finds recruiters at target firms, sends connection notes (10/day) |
| Recruiter Follow-up | `recruiter_service.py` | Messages recruiters who accepted connection (24h+ after accept) |
| Profile Views Connect | `profile_views_service.py` | Connects with people who viewed the profile (10/day) |
| Inbox Monitor | `inbox_monitor_service.py` | Checks LinkedIn messages for recruiter keywords; sends Telegram alert + AI draft reply |
| Company Watchlist | `company_watchlist_service.py` | Alerts on new co-op/internship postings from 10 target firms |
| Connection Tracker | `connection_tracker_service.py` | Checks if sent connections were accepted/declined (20 checks/day) |
| Interview Prep | `interview_prep_service.py` | Sends AI-generated prep package to Telegram when any app status → "interview" |
| Application Tracker | `application_tracker.py` | Tracks all jobs: seen/applied/responded/interview/offer/rejected |
| Health Status | `health_service.py` | Aggregates all state into one status dict for `/internal/status` |
| Weekly Digest | `weekly_digest_service.py` | Sunday Telegram summary with weekly deltas across all activity |
| Telegram Commands | `telegram_commands_service.py` | `/status`, `/applied`, `/update`, `/help` bot commands |

## Architecture

- **Flask app** (`app.py`) receives POST requests from cron-job.org
- Each endpoint starts a background `threading.Thread` and returns 200 immediately
- **Playwright** (headless Chromium) automates LinkedIn UI — cookies saved in `linkedin_cookies.json`
- **Claude Haiku** (`claude-haiku-4-5-20251001`) for all AI generation (job scoring, connection notes, cover letters, etc.)
- **Railway Volume** at `/data` for all persistent state (JSON files via `database.py`)
- **Telegram** for all notifications and alerts

## State Files (all in Railway Volume `/data`)

| File | Purpose |
|------|---------|
| `linkedin_cookies.json` | Session cookies for LinkedIn login |
| `linkedin_challenge_state.json` | Pending 2FA challenge URL |
| `connector_state.json` | `{date, connects_today, connected_ids[]}` |
| `alumni_connector_state.json` | `{date, sent_today, connected_ids[]}` |
| `recruiter_state.json` | `{date, sent_today, pending_followup[], messaged_ids[]}` |
| `profile_views_state.json` | `{date, sent_today, connected_viewer_ids[]}` |
| `engagement_state.json` | `{date, likes, comments}` |
| `easy_apply_state.json` | `{applied_ids[]}` |
| `inbox_state.json` | `{seen_thread_ids[last 500]}` |
| `application_tracker_state.json` | `{applications[]}` |
| `job_scraper_state.json` | `{seen_ids[]}` |
| `watchlist_state.json` | `{seen_ids[last 5000]}` |
| `connection_tracker_state.json` | `{pending[], accepted_count, declined_count}` |
| `interview_prep_state.json` | `{prepped_ids[]}` |
| `digest_state.json` | Weekly snapshot for delta calculations |
| `status_detector_state.json` | `{last_run, suggested_updates[]}` |
| `warmth_scores_state.json` | `{scores{}}` — per-profile engagement warmth scores |
| `notification_buffer_state.json` | `{buffer[], last_flush}` |
| `skill_profile_state.json` | `{skills[], target_roles[], updated_at}` |
| `keyword_alerts_state.json` | `{keywords[], alerted_job_ids[]}` |
| `feed_posts.json` | `{posts[], last_scraped}` — scraped LinkedIn feed posts |
| `job_archive_state.json` | `{archived[]}` — saved job descriptions |
| `games_state.json` | `{<game_id>: {won_date}}` — daily games completion tracking |
| `message_queue_state.json` | `{queue[]}` — scheduled message reminders |

## All Cron Jobs (cron-job.org)

API key: see cron-job.org dashboard (do not commit here)

| Job ID | Title | Schedule |
|--------|-------|---------|
| 7420093 | LinkedIn Job Scraper | 9:00 AM ET daily |
| 7420094 | LinkedIn Engagement | 11:00 AM ET weekdays |
| 7420096 | LinkedIn Connector | 10:00 AM ET Mon/Wed/Fri |
| 7426078 | LinkedIn Recruiter Outreach | 10:30 AM ET Mon/Wed/Fri |
| 7426079 | LinkedIn Recruiter Follow-up | 1:00 PM ET daily |
| 7426671 | LinkedIn Profile Views Connect | 11:00 AM ET daily |
| 7426672 | LinkedIn Inbox Monitor | 9:00 AM ET daily |
| 7427569 | LinkedIn Company Watchlist | 8:00 AM ET daily |
| 7427576 | LinkedIn Weekly Digest | 8:00 AM ET Sunday |
| 7427653 | LinkedIn Acceptance Check | 2:00 AM ET daily |
| 7429181 | LinkedIn Interview Prep | 3:00 PM ET daily |
| 7429182 | LinkedIn Alumni Connector | 10:00 AM ET Mon/Wed/Fri |
| 7432710 | LinkedIn Daily Games | 8:15 AM ET daily |

## All Endpoints

| Method | Path | What it does |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/internal/status?secret=` | Returns full bot status JSON |
| POST | `/internal/login-test?secret=` | Tests LinkedIn login |
| POST | `/internal/run-job-scraper?secret=` | Scrapes new jobs |
| POST | `/internal/run-engagement?secret=` | Likes + comments |
| POST | `/internal/run-connector?secret=` | Sends connection requests |
| POST | `/internal/run-recruiter?secret=` | Recruiter outreach |
| POST | `/internal/run-recruiter-followup?secret=` | Recruiter follow-ups |
| POST | `/internal/run-easy-apply?secret=` | Easy Apply batch |
| POST | `/internal/run-profile-views?secret=` | Profile views connect |
| POST | `/internal/run-inbox-check?secret=` | Inbox monitor |
| POST | `/internal/run-watchlist?secret=` | Company watchlist check |
| POST | `/internal/run-weekly-digest?secret=` | Weekly digest |
| POST | `/internal/run-acceptance-check?secret=` | Connection acceptance check |
| POST | `/internal/run-interview-prep?secret=` | Interview prep check |
| POST | `/internal/run-alumni-connector?secret=` | Alumni connector |
| POST | `/internal/telegram-command?secret=` | Telegram bot commands |
| POST | `/internal/linkedin-verify?secret=` | Submit LinkedIn 2FA code |
| POST | `/internal/linkedin-reset?secret=` | Reset LinkedIn session |
| POST | `/internal/track-application?secret=` | Manually track application |
| GET | `/internal/applications?secret=` | List all applications |
| POST | `/internal/check-follow-ups?secret=` | Check application follow-ups |

## Environment Variables (Railway)

| Var | Purpose |
|-----|---------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `LINKEDIN_EMAIL` | LinkedIn login email |
| `LINKEDIN_PASSWORD` | LinkedIn login password |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram user chat ID (set in Railway) |
| `SCHEDULER_SECRET` | Auth for all internal endpoints (set in Railway) |
| `DATA_DIR` | Volume mount path: `/data` |

## Coding Patterns

- **State pattern:** `database.load_state(filename, default={})` / `database.save_state(filename, data)`
- **Session pattern:** `with LinkedInSession() as session: page = session.new_page()`
- **Delays:** `from linkedin_session import random_delay; random_delay(2, 4)`
- **AI calls:** `anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())` with `claude-haiku-4-5-20251001`
- **Tests:** `unittest.mock.patch` (no pytest-mock); `conftest.py` sets all env vars including `DATA_DIR`
- **Background tasks:** `threading.Thread(target=fn, daemon=True).start()` then return 200

## Testing

```bash
cd c:/Users/sebas/linkedin-bot
python -m pytest tests/ -q          # run all (133 tests)
python -m pytest tests/test_foo.py  # single file
```

## Deploying

Push to `master` → Railway auto-deploys from GitHub.

```bash
git add -A && git commit -m "feat: ..." && git push origin master
```

## What's Left To Do

1. **Potential future features:**
   - Job description archiver (save descriptions for applied jobs)
   - Network analytics dashboard (acceptance rate over time)
   - Better engagement targeting (comment only on posts from target firms)
   - Telegram command to manually trigger any endpoint

## User Context

- **User:** Northeastern University sophomore, finance/fintech co-op hunting
- **Target firms:** Citadel, Jane Street, Point72, Two Sigma, Goldman Sachs, BlackRock, Fidelity, JPMorgan, Morgan Stanley, Robinhood, Stripe, Sequoia, General Catalyst
- **Goal:** Fully automated LinkedIn presence — scrape jobs, apply, network with recruiters and alumni, track pipeline

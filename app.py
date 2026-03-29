from flask import Flask, request, jsonify
import threading
import config
import database
from application_tracker import add_application, update_status, get_applications, check_follow_ups, format_applications_summary

app = Flask(__name__)


def _run_job_scraper():
    from linkedin_session import LinkedInSession
    from job_scraper import scrape_new_jobs, format_job_message
    from job_scorer import filter_and_score_jobs
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            jobs = scrape_new_jobs(session)
        if not jobs:
            print("[job_scraper] no new jobs", flush=True)
            return
        scored_jobs = filter_and_score_jobs(jobs, min_score=6)
        display_jobs = scored_jobs if scored_jobs else jobs[:10]
        header = f"💼 {len(scored_jobs)}/{len(jobs)} relevant co-op/internship listings:\n\n"
        send_telegram(header + "\n\n".join(format_job_message(j) for j in display_jobs[:10]))
        for job in jobs:
            try:
                add_application(job["job_id"], job["company"], job["title"], job.get("url", ""), status="seen")
            except Exception:
                pass
        print(f"[job_scraper] sent {len(jobs)} jobs", flush=True)
    except Exception as e:
        print(f"[job_scraper] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram
            send_telegram(f"❌ LinkedIn job scraper failed: {e}")
        except Exception:
            pass


def _run_engagement():
    from linkedin_session import LinkedInSession
    from engagement_service import run_daily_engagement
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            result = run_daily_engagement(session)
        send_telegram(f"✅ LinkedIn engagement: {result['liked']} likes, {result['commented']} comments")
    except Exception as e:
        print(f"[engagement] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram
            send_telegram(f"❌ LinkedIn engagement failed: {e}")
        except Exception:
            pass


def _run_connector():
    from linkedin_session import LinkedInSession
    from connector_service import run_daily_connections
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            count = run_daily_connections(session)
        send_telegram(f"🤝 LinkedIn connector: {count} connection requests sent")
    except Exception as e:
        print(f"[connector] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram
            send_telegram(f"❌ LinkedIn connector failed: {e}")
        except Exception:
            pass


def _run_recruiter_outreach():
    from linkedin_session import LinkedInSession
    from recruiter_service import run_recruiter_outreach
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            result = run_recruiter_outreach(session)
        send_telegram(f"🤝 Recruiter outreach: {result['sent']} connection requests sent")
    except Exception as e:
        print(f"[recruiter] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram
            send_telegram(f"❌ Recruiter outreach failed: {e}")
        except Exception:
            pass


def _run_recruiter_followup():
    from linkedin_session import LinkedInSession
    from recruiter_service import run_followup_check
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            result = run_followup_check(session)
        send_telegram(f"💬 Recruiter follow-ups: {result['messaged']} messages sent")
    except Exception as e:
        print(f"[recruiter_followup] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram
            send_telegram(f"❌ Recruiter follow-up failed: {e}")
        except Exception:
            pass


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/internal/login-test", methods=["POST"])
def login_test():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403

    def _test():
        from linkedin_session import LinkedInSession
        from telegram_service import send_telegram
        try:
            with LinkedInSession() as session:
                page = session.new_page()
                page.goto("https://www.linkedin.com/feed/", timeout=20000)
                url = page.url
                page.close()
            send_telegram(f"✅ LinkedIn login OK — landed on: {url}")
        except Exception as e:
            send_telegram(f"❌ LinkedIn login test failed: {e}")

    threading.Thread(target=_test, daemon=True).start()
    return jsonify({"status": "ok", "message": "login test started"})


@app.route("/internal/run-job-scraper", methods=["POST"])
def run_job_scraper():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_job_scraper, daemon=True).start()
    return jsonify({"status": "ok", "message": "job scraper started"})


@app.route("/internal/run-engagement", methods=["POST"])
def run_engagement():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_engagement, daemon=True).start()
    return jsonify({"status": "ok", "message": "engagement started"})


@app.route("/internal/run-connector", methods=["POST"])
def run_connector():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_connector, daemon=True).start()
    return jsonify({"status": "ok", "message": "connector started"})


def _run_verify(code: str):
    from linkedin_session import LinkedInSession, random_delay
    from telegram_service import send_telegram
    try:
        challenge_state = database.load_state("linkedin_challenge_state.json", default={})
        if not challenge_state.get("challenge_url"):
            send_telegram("❌ No pending LinkedIn challenge found.")
            return

        # Start fresh session with saved cookies
        with LinkedInSession() as session:
            page = session.new_page()
            page.goto(challenge_state["challenge_url"], timeout=20000)
            random_delay(2, 3)

            # Try to find and fill the verification code input
            # LinkedIn uses different selectors for different challenge types
            for selector in ["input[name='pin']", "input[id*='input']", "input[type='text']"]:
                try:
                    page.fill(selector, code, timeout=3000)
                    random_delay(0.5, 1.0)
                    break
                except Exception:
                    continue

            # Submit
            for selector in ["button[type='submit']", "button:has-text('Submit')", "button:has-text('Verify')"]:
                try:
                    page.click(selector, timeout=3000)
                    break
                except Exception:
                    continue

            page.wait_for_load_state("networkidle", timeout=15000)
            random_delay(2, 4)

            if "feed" in page.url or "mynetwork" in page.url:
                database.save_state("linkedin_challenge_state.json", {})
                send_telegram(f"✅ LinkedIn verification successful! Logged in at {page.url}")
            else:
                send_telegram(f"⚠️ Verification attempt result: {page.url}. Code may be wrong or expired.")
            page.close()
    except Exception as e:
        send_telegram(f"❌ LinkedIn verify error: {e}")
        print(f"[verify] error: {e}", flush=True)


@app.route("/internal/linkedin-verify", methods=["POST"])
def linkedin_verify():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    data = request.get_json(force=True, silent=True) or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "code required"}), 400
    threading.Thread(target=_run_verify, args=(code,), daemon=True).start()
    return jsonify({"status": "ok", "message": "verification started"})


@app.route("/internal/linkedin-reset", methods=["POST"])
def linkedin_reset():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    database.save_state("linkedin_cookies.json", [])
    database.save_state("linkedin_challenge_state.json", {})
    return jsonify({"status": "ok", "message": "LinkedIn session reset"})


@app.route("/internal/track-application", methods=["POST"])
def track_application():
    """Manually mark a job as applied."""
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    data = request.get_json(force=True, silent=True) or {}
    job_id = data.get("job_id", "")
    company = data.get("company", "")
    title = data.get("title", "")
    url = data.get("url", "")
    if not job_id or not company or not title:
        return jsonify({"error": "job_id, company, title required"}), 400
    msg = add_application(job_id, company, title, url)
    return jsonify({"status": "ok", "message": msg})


@app.route("/internal/applications", methods=["GET"])
def list_applications():
    """List all tracked applications."""
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    apps = get_applications()
    return jsonify({"applications": apps, "count": len(apps)})


def _run_follow_up_check():
    from telegram_service import send_telegram
    try:
        messages = check_follow_ups()
        for msg in messages:
            send_telegram(msg)
        print(f"[follow_up] sent {len(messages)} follow-up reminders", flush=True)
    except Exception as e:
        print(f"[follow_up] error: {e}", flush=True)


@app.route("/internal/check-follow-ups", methods=["POST"])
def check_follow_ups_endpoint():
    """Check for applications needing follow-up (run daily)."""
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_follow_up_check, daemon=True).start()
    return jsonify({"status": "ok", "message": "follow-up check started"})


@app.route("/internal/run-recruiter", methods=["POST"])
def run_recruiter():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_recruiter_outreach, daemon=True).start()
    return jsonify({"status": "ok", "message": "recruiter outreach started"})


@app.route("/internal/run-recruiter-followup", methods=["POST"])
def run_recruiter_followup():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_recruiter_followup, daemon=True).start()
    return jsonify({"status": "ok", "message": "recruiter follow-up started"})


def _run_easy_apply():
    from linkedin_session import LinkedInSession
    from easy_apply_service import run_easy_apply_batch
    from application_tracker import get_applications
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            jobs = get_applications(status_filter="seen")
            result = run_easy_apply_batch(session, jobs)
        send_telegram(f"📝 Easy Apply: {result['applied']} submitted, {result['skipped']} skipped")
    except Exception as e:
        print(f"[easy_apply] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram
            send_telegram(f"❌ Easy Apply failed: {e}")
        except Exception:
            pass


def _run_profile_views():
    from linkedin_session import LinkedInSession
    from profile_views_service import run_profile_views_connect
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            result = run_profile_views_connect(session)
        send_telegram(f"👀 Profile views: {result['sent']} connections sent ({result['checked']} checked)")
    except Exception as e:
        print(f"[profile_views] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram
            send_telegram(f"❌ Profile views connect failed: {e}")
        except Exception:
            pass


def _run_inbox_check():
    from linkedin_session import LinkedInSession
    from inbox_monitor_service import run_inbox_check
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            result = run_inbox_check(session)
        if result['notified'] == 0:
            print(f"[inbox] checked {result['found']} threads, no recruiter messages", flush=True)
    except Exception as e:
        print(f"[inbox] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram
            send_telegram(f"❌ Inbox check failed: {e}")
        except Exception:
            pass


@app.route("/internal/run-easy-apply", methods=["POST"])
def run_easy_apply():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_easy_apply, daemon=True).start()
    return jsonify({"status": "ok", "message": "easy apply started"})


@app.route("/internal/run-profile-views", methods=["POST"])
def run_profile_views():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_profile_views, daemon=True).start()
    return jsonify({"status": "ok", "message": "profile views connect started"})


@app.route("/internal/run-inbox-check", methods=["POST"])
def run_inbox_check_endpoint():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_inbox_check, daemon=True).start()
    return jsonify({"status": "ok", "message": "inbox check started"})


def _run_watchlist_check():
    from linkedin_session import LinkedInSession
    from company_watchlist_service import run_watchlist_check
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            result = run_watchlist_check(session)
        print(f"[watchlist] {result['alerts_sent']} alerts, {result['companies_checked']} companies checked", flush=True)
    except Exception as e:
        print(f"[watchlist] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram
            send_telegram(f"❌ Watchlist check failed: {e}")
        except Exception:
            pass


def _run_weekly_digest():
    from weekly_digest_service import run_weekly_digest
    from telegram_service import send_telegram
    try:
        run_weekly_digest()
        print("[weekly_digest] sent", flush=True)
    except Exception as e:
        print(f"[weekly_digest] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram
            send_telegram(f"❌ Weekly digest failed: {e}")
        except Exception:
            pass


@app.route("/internal/status", methods=["GET"])
def status():
    from health_service import get_status
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    return jsonify(get_status())


@app.route("/internal/run-watchlist", methods=["POST"])
def run_watchlist():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_watchlist_check, daemon=True).start()
    return jsonify({"status": "ok", "message": "watchlist check started"})


@app.route("/internal/run-weekly-digest", methods=["POST"])
def run_weekly_digest_endpoint():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_weekly_digest, daemon=True).start()
    return jsonify({"status": "ok", "message": "weekly digest started"})


if __name__ == "__main__":
    app.run(debug=True)

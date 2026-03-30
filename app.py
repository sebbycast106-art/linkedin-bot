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
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            jobs = scrape_new_jobs(session)
        if not jobs:
            print("[job_scraper] no new jobs", flush=True)
            return
        scored_jobs = filter_and_score_jobs(jobs, min_score=6)
        display_jobs = scored_jobs if scored_jobs else jobs[:10]
        send_telegram(block("JOBS", [
            ("scraped",   len(jobs)),
            ("relevant",  f"{len(scored_jobs)}  (score ≥6)"),
            ("showing",   len(display_jobs)),
        ]))
        send_telegram("\n\n".join(format_job_message(j) for j in display_jobs[:10]), parse_mode="HTML")
        for job in jobs:
            try:
                add_application(job["job_id"], job["company"], job["title"], job.get("url", ""), status="seen")
            except Exception:
                pass
        print(f"[job_scraper] sent {len(jobs)} jobs", flush=True)
    except Exception as e:
        print(f"[job_scraper] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("JOBS [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


def _run_engagement():
    from linkedin_session import LinkedInSession
    from engagement_service import run_daily_engagement
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            result = run_daily_engagement(session)
        send_telegram(block("ENGAGEMENT", [
            ("liked",     result['liked']),
            ("commented", result['commented']),
        ]))
    except Exception as e:
        print(f"[engagement] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("ENGAGEMENT [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


def _run_connector():
    from linkedin_session import LinkedInSession
    from connector_service import run_daily_connections
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            count = run_daily_connections(session)
        send_telegram(block("CONNECTOR", [
            ("sent",  f"{count}  requests"),
        ]))
    except Exception as e:
        print(f"[connector] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("CONNECTOR [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


def _run_recruiter_outreach():
    from linkedin_session import LinkedInSession
    from recruiter_service import run_recruiter_outreach
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            result = run_recruiter_outreach(session)
        send_telegram(block("RECRUITER", [
            ("sent",    f"{result['sent']}  connection requests"),
        ]))
    except Exception as e:
        print(f"[recruiter] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("RECRUITER [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


def _run_recruiter_followup():
    from linkedin_session import LinkedInSession
    from recruiter_service import run_followup_check
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            result = run_followup_check(session)
        send_telegram(block("RECRUITER FOLLOWUP", [
            ("messaged", f"{result['messaged']}  messages sent"),
        ]))
    except Exception as e:
        print(f"[recruiter_followup] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("RECRUITER FOLLOWUP [err]", [("reason", str(e)[:80])]))
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
            from telegram_service import block
            send_telegram(block("LOGIN TEST", [
                ("status",  "OK"),
                ("landed",  url[:60]),
            ]))
        except Exception as e:
            from telegram_service import block
            send_telegram(block("LOGIN TEST [err]", [("reason", str(e)[:80])]))

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
    from telegram_service import send_telegram, block
    try:
        challenge_state = database.load_state("linkedin_challenge_state.json", default={})
        if not challenge_state.get("challenge_url"):
            send_telegram(block("VERIFY [err]", [("reason", "no pending challenge found")]))
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
                send_telegram(block("VERIFY", [
                    ("status",  "OK  session active"),
                    ("url",     page.url[:60]),
                ]))
            else:
                send_telegram(block("VERIFY [warn]", [
                    ("status",  "code may be wrong or expired"),
                    ("url",     page.url[:60]),
                ]))
            page.close()
    except Exception as e:
        send_telegram(block("VERIFY [err]", [("reason", str(e)[:80])]))
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
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            jobs = get_applications(status_filter="seen")
            result = run_easy_apply_batch(session, jobs)
        send_telegram(block("EASY APPLY", [
            ("submitted", result['applied']),
            ("skipped",   result['skipped']),
        ]))
    except Exception as e:
        print(f"[easy_apply] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("EASY APPLY [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


def _run_profile_views():
    from linkedin_session import LinkedInSession
    from profile_views_service import run_profile_views_connect
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            result = run_profile_views_connect(session)
        send_telegram(block("PROFILE VIEWS", [
            ("checked",  result['checked']),
            ("sent",     f"{result['sent']}  connection requests"),
        ]))
    except Exception as e:
        print(f"[profile_views] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("PROFILE VIEWS [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


def _run_inbox_check():
    from linkedin_session import LinkedInSession
    from inbox_monitor_service import run_inbox_check
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            result = run_inbox_check(session)
        if result['notified'] == 0:
            print(f"[inbox] checked {result['found']} threads, no recruiter messages", flush=True)
        else:
            send_telegram(block("INBOX", [
                ("threads",  result['found']),
                ("alerted",  f"{result['notified']}  recruiter messages"),
            ]))
    except Exception as e:
        print(f"[inbox] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("INBOX [err]", [("reason", str(e)[:80])]))
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
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            result = run_watchlist_check(session)
        if result['alerts_sent'] > 0:
            send_telegram(block("WATCHLIST", [
                ("checked",  f"{result['companies_checked']}  companies"),
                ("alerts",   f"{result['alerts_sent']}  new postings"),
            ]))
        else:
            print(f"[watchlist] {result['companies_checked']} companies checked, no new postings", flush=True)
    except Exception as e:
        print(f"[watchlist] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("WATCHLIST [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


def _run_weekly_digest():
    from weekly_digest_service import run_weekly_digest
    try:
        run_weekly_digest()
        print("[weekly_digest] sent", flush=True)
    except Exception as e:
        print(f"[weekly_digest] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("WEEKLY DIGEST [err]", [("reason", str(e)[:80])]))
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


def _run_acceptance_check():
    from linkedin_session import LinkedInSession
    from connection_tracker_service import run_acceptance_check
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            result = run_acceptance_check(session)
        if result['accepted'] > 0:
            send_telegram(block("CONNECTIONS", [
                ("accepted",  result['accepted']),
                ("pending",   result['still_pending']),
            ]))
        else:
            print(f"[acceptance_check] {result['accepted']} accepted, {result['still_pending']} pending", flush=True)
    except Exception as e:
        print(f"[acceptance_check] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("CONNECTIONS [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


@app.route("/internal/run-acceptance-check", methods=["POST"])
def run_acceptance_check_endpoint():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_acceptance_check, daemon=True).start()
    return jsonify({"status": "ok", "message": "acceptance check started"})


@app.route("/internal/telegram-command", methods=["POST"])
def telegram_command():
    """Handle inbound Telegram message commands."""
    from telegram_commands_service import handle_telegram_command
    from telegram_service import send_telegram
    data = request.get_json(force=True, silent=True) or {}
    text = ""
    try:
        text = data["message"]["text"]
    except (KeyError, TypeError):
        pass
    if not text:
        return jsonify({"status": "ok"})
    reply = handle_telegram_command(text)
    if reply:
        send_telegram(reply)
    return jsonify({"status": "ok"})


def _run_interview_prep_check():
    from interview_prep_service import run_interview_prep_check
    try:
        result = run_interview_prep_check()
        print(f"[interview_prep] {result['prepped']} prep packages sent", flush=True)
    except Exception as e:
        print(f"[interview_prep] error: {e}", flush=True)


def _run_alumni_connections():
    from linkedin_session import LinkedInSession
    from alumni_connector_service import run_alumni_connections
    from telegram_service import send_telegram, block
    try:
        with LinkedInSession() as session:
            result = run_alumni_connections(session)
        send_telegram(block("ALUMNI CONNECTOR", [
            ("checked", result['checked']),
            ("sent",    f"{result['sent']}  connection requests"),
        ]))
    except Exception as e:
        print(f"[alumni_connector] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("ALUMNI CONNECTOR [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


@app.route("/internal/run-interview-prep", methods=["POST"])
def run_interview_prep():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_interview_prep_check, daemon=True).start()
    return jsonify({"status": "ok", "message": "interview prep check started"})


@app.route("/internal/analytics", methods=["GET"])
def analytics():
    from analytics_service import compute_analytics
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    return jsonify(compute_analytics())


@app.route("/internal/run-alumni-connector", methods=["POST"])
def run_alumni_connector():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_alumni_connections, daemon=True).start()
    return jsonify({"status": "ok", "message": "alumni connector started"})


def _run_stale_check():
    from stale_app_service import run_stale_check
    try:
        result = run_stale_check()
        print(f"[stale_check] {result['stale_count']} stale, notified={result['notified']}", flush=True)
    except Exception as e:
        print(f"[stale_check] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("STALE CHECK [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


def _run_keyword_alerts():
    from keyword_alert_service import run_keyword_alerts
    try:
        result = run_keyword_alerts()
        print(f"[keyword_alerts] matched={result['matched']}, alerted={result['alerted']}", flush=True)
    except Exception as e:
        print(f"[keyword_alerts] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("KEYWORD ALERTS [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


def _run_flush_notifications():
    from notification_service import flush_notifications
    try:
        result = flush_notifications()
        print(f"[notifications] flushed {result['sent']} notifications", flush=True)
    except Exception as e:
        print(f"[notifications] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("NOTIFICATIONS [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


@app.route("/internal/run-stale-check", methods=["POST"])
def run_stale_check_endpoint():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_stale_check, daemon=True).start()
    return jsonify({"status": "ok", "message": "stale check started"})


@app.route("/internal/run-keyword-alerts", methods=["POST"])
def run_keyword_alerts_endpoint():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_keyword_alerts, daemon=True).start()
    return jsonify({"status": "ok", "message": "keyword alerts started"})


@app.route("/internal/flush-notifications", methods=["POST"])
def flush_notifications_endpoint():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_flush_notifications, daemon=True).start()
    return jsonify({"status": "ok", "message": "notification flush started"})


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m{s % 60:02d}s"


def _run_games_task():
    from games_service import run_all_games
    from telegram_service import send_telegram, block
    try:
        results = run_all_games()
        rows = []
        total_elapsed = 0.0
        won_count = 0
        for game_id, info in results.items():
            if isinstance(info, dict):
                won      = info.get("won", False)
                skipped  = info.get("skipped", False)
                elapsed  = info.get("elapsed", 0.0)
            else:
                won, skipped, elapsed = bool(info), False, 0.0
            total_elapsed += elapsed
            if won:
                won_count += 1
            status = "already done" if skipped else ("solved" if won else "FAILED")
            rows.append((game_id, f"{status:<16}{_fmt_elapsed(elapsed) if not skipped else ''}"))
        total = len(results)
        note = f"{won_count}/{total}  complete   total {_fmt_elapsed(total_elapsed)}"
        send_telegram(block("GAMES", rows, note=note))
    except Exception as e:
        print(f"[games] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("GAMES [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


@app.route("/internal/run-games", methods=["POST"])
def run_games():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_games_task, daemon=True).start()
    return jsonify({"status": "ok", "message": "games started"})


def _run_status_detector():
    from app_status_detector_service import run_status_detection
    try:
        result = run_status_detection()
        print(f"[status_detector] detected={result['detected']} suggested={result['suggested']}", flush=True)
    except Exception as e:
        print(f"[status_detector] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("STATUS DETECTOR [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


def _run_message_queue():
    from message_scheduler_service import run_message_queue
    try:
        result = run_message_queue()
        print(f"[message_queue] reminded={result['reminded']} expired={result['expired']}", flush=True)
    except Exception as e:
        print(f"[message_queue] error: {e}", flush=True)
        try:
            from telegram_service import send_telegram, block
            send_telegram(block("MESSAGE QUEUE [err]", [("reason", str(e)[:80])]))
        except Exception:
            pass


@app.route("/internal/run-status-detector", methods=["POST"])
def run_status_detector_endpoint():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_status_detector, daemon=True).start()
    return jsonify({"status": "ok", "message": "status detector started"})


@app.route("/internal/run-message-queue", methods=["POST"])
def run_message_queue_endpoint():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_message_queue, daemon=True).start()
    return jsonify({"status": "ok", "message": "message queue started"})


@app.route("/internal/warmth-scores", methods=["GET"])
def warmth_scores():
    """Return warmth scores JSON."""
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    from warmth_scorer_service import get_warmth_scores
    return jsonify({"warmth_scores": get_warmth_scores()})


@app.route("/internal/run-skill-match", methods=["POST"])
def run_skill_match():
    """Return skill profile info."""
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    from skill_match_service import get_skill_profile
    return jsonify({"status": "ok", "profile": get_skill_profile()})


@app.route("/internal/job-archive", methods=["GET"])
def job_archive():
    """Return all archived job descriptions."""
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    from job_archive_service import get_all_archived
    return jsonify({"archived": get_all_archived()})


if __name__ == "__main__":
    app.run(debug=True)


@app.route("/internal/run-feed-scrape", methods=["POST"])
def run_feed_scrape():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    def _task():
        from feed_scraper_service import run_feed_scrape as _scrape
        from linkedin_session import LinkedInSession
        try:
            with LinkedInSession() as session:
                result = _scrape(session)
            print(f"[feed_scraper] done: {result}", flush=True)
        except Exception as e:
            print(f"[feed_scraper] error: {e}", flush=True)
    threading.Thread(target=_task, daemon=True).start()
    return jsonify({"status": "ok", "message": "feed scrape started"})


@app.route("/internal/posts", methods=["GET"])
def get_posts():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    from feed_scraper_service import get_posts as _get_posts
    import database as _db
    limit = min(int(request.args.get("limit", 50)), 100)
    posts = _get_posts(limit=limit)
    state = _db.load_state("feed_posts.json", default={})
    return jsonify({
        "posts": posts,
        "total": len(posts),
        "last_scraped": state.get("last_scraped"),
    })

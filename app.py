from flask import Flask, request, jsonify
import threading
import config

app = Flask(__name__)


def _run_job_scraper():
    from linkedin_session import LinkedInSession
    from job_scraper import scrape_new_jobs, format_job_message
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            jobs = scrape_new_jobs(session)
        if not jobs:
            print("[job_scraper] no new jobs", flush=True)
            return
        header = f"💼 {len(jobs)} new co-op/internship listings:\n\n"
        send_telegram(header + "\n\n".join(format_job_message(j) for j in jobs[:10]))
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


if __name__ == "__main__":
    app.run(debug=True)

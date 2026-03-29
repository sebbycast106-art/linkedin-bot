"""
easy_apply_service.py — Submit LinkedIn Easy Apply applications.

Only handles simple single-step Easy Apply forms. Skips multi-step or complex forms.
Daily limit: 5 applications per run to avoid spam detection.

Public interface:
    try_easy_apply(page, job_url) -> bool
    run_easy_apply_batch(session, jobs: list) -> dict  # {"applied": N, "skipped": N, "errors": N}
"""
import database
import job_scorer
from linkedin_session import random_delay
from application_tracker import add_application

_STATE_FILE = "easy_apply_state.json"
_DAILY_LIMIT = 5
_PHONE_NUMBER = "6175551234"


def try_easy_apply(page, job_url: str) -> bool:
    """
    Attempt to submit an Easy Apply application for a job.

    Returns True if successfully applied, False if skipped or failed.
    """
    result = False
    try:
        page.goto(job_url, timeout=20000)
        random_delay(2, 3)

        # Score full job description before attempting apply
        title_from_page = ""
        company_from_page = ""
        try:
            t = page.query_selector("h1.job-details-jobs-unified-top-card__job-title, h1.jobs-unified-top-card__job-title")
            title_from_page = t.inner_text().strip() if t else ""
            c = page.query_selector(".job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name")
            company_from_page = c.inner_text().strip() if c else ""
        except Exception:
            pass

        description = job_scorer.scrape_job_description(page, job_url)
        if description:
            desc_score = job_scorer.score_job_description(title_from_page, company_from_page, description)
            if desc_score < 7:
                print(f"[easy_apply] {job_url[:60]}: description score {desc_score}/10 — skipping", flush=True)
                return False

        # Look for Easy Apply button
        easy_apply_btn = page.query_selector("button[aria-label*='Easy Apply']")
        if not easy_apply_btn:
            print(f"[easy_apply] {job_url[:60]}: skipped", flush=True)
            return False

        easy_apply_btn.click()
        random_delay(1, 2)

        # Check for multi-step indicator
        form_sections = page.query_selector_all("li.jobs-easy-apply-form-section__grouping")
        pagination = page.query_selector(".artdeco-pagination")
        if len(form_sections) > 2 or pagination:
            # Complex multi-step form — dismiss
            dismiss_btn = page.query_selector("button[aria-label='Dismiss']")
            if dismiss_btn:
                dismiss_btn.click()
            print(f"[easy_apply] {job_url[:60]}: skipped", flush=True)
            return False

        # Try to fill phone if empty
        phone_input = page.query_selector(
            "input[id*='phoneNumber'], input[name*='phoneNumber'], input[type='tel']"
        )
        if phone_input:
            current_value = phone_input.input_value() if hasattr(phone_input, "input_value") else ""
            if not current_value:
                phone_input.fill(_PHONE_NUMBER)

        # Check for required fields we can't fill
        file_upload = page.query_selector("input[type='file']")
        if file_upload:
            dismiss_btn = page.query_selector("button[aria-label='Dismiss']")
            if dismiss_btn:
                dismiss_btn.click()
            print(f"[easy_apply] {job_url[:60]}: skipped", flush=True)
            return False

        # Check for cover letter textarea — generate and fill instead of skipping
        textareas = page.query_selector_all("textarea")
        for textarea in textareas:
            label_text = ""
            try:
                label_text = textarea.get_attribute("aria-label") or ""
            except Exception:
                pass
            if "cover" in label_text.lower():
                cover_text = None
                try:
                    from ai_service import generate_cover_letter
                    cover_text = generate_cover_letter(title_from_page, company_from_page, description or "")
                except Exception:
                    pass
                if cover_text:
                    try:
                        textarea.fill(cover_text)
                        random_delay(0.5, 1.0)
                    except Exception:
                        pass
                # Don't skip — continue with the rest of the form
                break

        # Check for Review button (multi-step) — skip
        review_btn = page.query_selector("button[aria-label*='Review']")
        if review_btn:
            dismiss_btn = page.query_selector("button[aria-label='Dismiss']")
            if dismiss_btn:
                dismiss_btn.click()
            print(f"[easy_apply] {job_url[:60]}: skipped", flush=True)
            return False

        # Click submit button
        submit_btn = page.query_selector("button[aria-label*='Submit application']")
        if not submit_btn:
            dismiss_btn = page.query_selector("button[aria-label='Dismiss']")
            if dismiss_btn:
                dismiss_btn.click()
            print(f"[easy_apply] {job_url[:60]}: skipped", flush=True)
            return False

        submit_btn.click()
        random_delay(2, 3)

        # Check for success indicators
        success_el = page.query_selector(".artdeco-inline-feedback--success")
        if success_el:
            result = True
        else:
            # Check page content for success text
            try:
                content = page.content()
                if "application was sent" in content.lower():
                    result = True
            except Exception:
                pass

            # Check URL change as fallback
            if not result:
                try:
                    current_url = page.url
                    if current_url != job_url:
                        result = True
                except Exception:
                    pass

    except Exception as e:
        print(f"[easy_apply] error on {job_url[:60]}: {e}", flush=True)
        try:
            dismiss_btn = page.query_selector("button[aria-label='Dismiss']")
            if dismiss_btn:
                dismiss_btn.click()
        except Exception:
            pass
        result = False

    print(f"[easy_apply] {job_url[:60]}: {'applied' if result else 'skipped'}", flush=True)
    return result


def run_easy_apply_batch(session, jobs: list) -> dict:
    """
    Run Easy Apply for a batch of jobs.

    jobs: list of dicts with keys: job_id, company, title, url
    Returns: {"applied": N, "skipped": N, "errors": N}
    """
    counts = {"applied": 0, "skipped": 0, "errors": 0}

    try:
        # Load state
        state = database.load_state(_STATE_FILE, default={"applied_ids": []})
        applied_ids = set(state.get("applied_ids", []))

        page = session.new_page()
        attempted_this_run = 0

        for job in jobs:
            if attempted_this_run >= _DAILY_LIMIT:
                counts["skipped"] += 1
                continue

            job_id = job.get("job_id", "")
            if job_id in applied_ids:
                counts["skipped"] += 1
                continue

            attempted_this_run += 1
            try:
                success = try_easy_apply(page, job["url"])
                if success:
                    add_application(
                        job_id,
                        job.get("company", ""),
                        job.get("title", ""),
                        job.get("url", ""),
                        status="applied",
                    )
                    applied_ids.add(job_id)
                    counts["applied"] += 1
                # not-applicable (no Easy Apply / multi-step) not counted
            except Exception as e:
                print(f"[easy_apply] batch error for {job_id}: {e}", flush=True)
                counts["errors"] += 1

            if attempted_this_run < _DAILY_LIMIT:
                random_delay(10, 20)

        # Save updated state
        state["applied_ids"] = list(applied_ids)
        database.save_state(_STATE_FILE, state)

    except Exception as e:
        print(f"[easy_apply] run_easy_apply_batch error: {e}", flush=True)
        counts["errors"] += 1

    return counts

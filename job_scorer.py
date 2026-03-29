"""
job_scorer.py — Score job listings by relevance using Claude AI.

Public interface:
    score_job(title: str, company: str) -> int  # 1-10
    score_job_description(title: str, company: str, description: str) -> int  # 1-10
    scrape_job_description(page, job_url: str) -> str
    filter_and_score_jobs(jobs: list, min_score: int = 6) -> list[dict]
"""
import anthropic
import config

_PROMPT_TEMPLATE = """You are helping a Northeastern University sophomore find finance/fintech co-ops and internships.

Score this job listing 1-10 for relevance:
Title: {title}
Company: {company}

Scoring guide:
- 9-10: Perfect fit — finance/fintech/business co-op or internship at reputable firm
- 7-8: Good fit — related field (consulting, accounting, data) or strong company
- 5-6: Okay — tangentially related or unclear
- 1-4: Poor fit — unrelated field, sketchy company, or not actually an internship/co-op

Reply with ONLY a single integer 1-10. Nothing else."""


def score_job(title: str, company: str) -> int:
    """Score a job listing 1-10 for relevance using Claude AI."""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = _PROMPT_TEMPLATE.format(title=title, company=company)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": prompt}],
        )
        score = int(response.content[0].text.strip())
        print(f"[job_scorer] {title[:40]} @ {company[:20]}: {score}", flush=True)
        return score
    except Exception as e:
        print(f"[job_scorer] scoring error for '{title[:40]}': {e}", flush=True)
        return 5


_DESC_PROMPT_TEMPLATE = """You are helping a Northeastern University sophomore find finance/fintech co-ops and internships.

Score this job 1-10 for fit:
Title: {title}
Company: {company}
Description: {description}

Scoring guide:
- 9-10: Perfect fit — finance/fintech/business co-op or internship, clear match for skills, reputable firm
- 7-8: Good fit — related field (consulting, data, accounting) or strong company
- 5-6: Okay — tangentially related, unclear requirements, or mixed signals
- 1-4: Poor fit — wrong field, requires experience we don't have, not actually entry-level/co-op

Key disqualifiers (score 1-3):
- Requires 2+ years experience
- Purely technical (software engineering, ML) with no business component
- Commission-only or insurance sales
- Located outside US

Reply with ONLY a single integer 1-10. Nothing else."""


def score_job_description(title: str, company: str, description: str) -> int:
    """Score a job listing 1-10 for relevance using its full description."""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = _DESC_PROMPT_TEMPLATE.format(
            title=title, company=company, description=description[:1500]
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": prompt}],
        )
        score = int(response.content[0].text.strip())
        print(f"[job_scorer] description score for {title[:40]}: {score}", flush=True)
        return score
    except Exception as e:
        print(f"[job_scorer] description scoring error for '{title[:40]}': {e}", flush=True)
        return 5


def scrape_job_description(page, job_url: str) -> str:
    """Navigate to job URL and return the job description text (up to 2000 chars)."""
    try:
        page.goto(job_url, timeout=20000)
        page.wait_for_selector(
            ".jobs-description, .job-details-module", timeout=8000
        )
        for selector in (
            ".jobs-description__content",
            ".job-details-module__content",
            ".jobs-box__html-content",
        ):
            el = page.query_selector(selector)
            if el:
                return el.inner_text()[:2000]
        return ""
    except Exception:
        return ""


def filter_and_score_jobs(jobs: list, min_score: int = 6) -> list[dict]:
    """Score each job and return those meeting min_score, sorted descending."""
    scored = []
    for job in jobs:
        job = dict(job)
        job["score"] = score_job(job["title"], job["company"])
        scored.append(job)

    result = [j for j in scored if j["score"] >= min_score]
    result.sort(key=lambda j: j["score"], reverse=True)
    print(f"[job_scorer] filtered {len(result)}/{len(jobs)} jobs (min_score={min_score})", flush=True)
    return result

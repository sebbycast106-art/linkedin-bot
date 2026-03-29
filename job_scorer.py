"""
job_scorer.py — Score job listings by relevance using Claude AI.

Public interface:
    score_job(title: str, company: str) -> int  # 1-10
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

"""
skill_match_service.py — Score jobs against user's skill profile using Claude AI.

Public interface:
    score_job_match(title, company, description) -> int  # 0-100
    get_skill_profile() -> dict
    update_skill_profile(skills=None, target_roles=None) -> str
"""
import anthropic
import config
import database
from datetime import datetime, timezone

_STATE_FILE = "skill_profile_state.json"

_DEFAULT_SKILLS = [
    "financial modeling", "data analysis", "python", "excel",
    "bloomberg", "accounting", "valuation", "risk management",
]

_DEFAULT_TARGET_ROLES = [
    "quantitative analyst", "investment banking", "fintech", "trading",
    "portfolio management", "financial analyst", "business analyst", "venture capital",
]


def _default_profile() -> dict:
    return {
        "skills": list(_DEFAULT_SKILLS),
        "target_roles": list(_DEFAULT_TARGET_ROLES),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_profile() -> dict:
    profile = database.load_state(_STATE_FILE, default=_default_profile())
    if not profile.get("skills"):
        profile = _default_profile()
    return profile


def _save_profile(profile: dict) -> None:
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    database.save_state(_STATE_FILE, profile)


def score_job_match(title: str, company: str, description: str) -> int:
    """Score how well a job matches the user's skill profile (0-100).

    Uses Claude Haiku to evaluate overlap between user skills/target roles
    and the job posting. Returns 50 on any error as a neutral fallback.
    """
    try:
        profile = _load_profile()
        skills_str = ", ".join(profile.get("skills", _DEFAULT_SKILLS))
        roles_str = ", ".join(profile.get("target_roles", _DEFAULT_TARGET_ROLES))

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = (
            f"You are evaluating job fit for a candidate.\n\n"
            f"Candidate skills: {skills_str}\n"
            f"Target roles: {roles_str}\n\n"
            f"Job title: {title}\n"
            f"Company: {company}\n"
            f"Job description: {description[:1500]}\n\n"
            f"Score this job 0-100 based on how well it matches the candidate's "
            f"skills and target roles. Consider skill overlap, role relevance, "
            f"and growth potential.\n\n"
            f"Reply with ONLY a single integer 0-100. Nothing else."
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        score = int(text)
        return max(0, min(100, score))
    except Exception as e:
        print(f"[skill_match] score_job_match error: {e}", flush=True)
        return 50


def get_skill_profile() -> dict:
    """Return the current skill profile dict."""
    return _load_profile()


def update_skill_profile(skills: list = None, target_roles: list = None) -> str:
    """Update the skill profile. Returns a confirmation message."""
    profile = _load_profile()
    changes = []

    if skills is not None:
        profile["skills"] = skills
        changes.append(f"{len(skills)} skills")

    if target_roles is not None:
        profile["target_roles"] = target_roles
        changes.append(f"{len(target_roles)} target roles")

    _save_profile(profile)
    return f"Updated skill profile: {', '.join(changes)}"

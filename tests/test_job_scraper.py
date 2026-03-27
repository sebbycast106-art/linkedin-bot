import job_scraper

def test_format_job_message():
    job = {
        "title": "Finance Co-op",
        "company": "Fidelity Investments",
        "location": "Boston, MA",
        "url": "https://www.linkedin.com/jobs/view/123",
        "job_id": "123",
    }
    msg = job_scraper.format_job_message(job)
    assert "Finance Co-op" in msg
    assert "Fidelity" in msg
    assert "Boston" in msg
    assert "linkedin.com" in msg

def test_is_new_job_returns_true_for_unseen():
    assert job_scraper.is_new_job("abc123", set()) is True

def test_is_new_job_returns_false_for_seen():
    assert job_scraper.is_new_job("abc123", {"abc123"}) is False

def test_build_search_url_contains_keywords():
    url = job_scraper.build_search_url(keywords="co-op finance", location="Boston, MA")
    assert "linkedin.com" in url
    assert "co-op" in url or "co%2Dop" in url or "co+op" in url

def test_build_search_url_contains_location():
    url = job_scraper.build_search_url(keywords="internship", location="New York")
    assert "New+York" in url or "New%20York" in url or "New York" in url

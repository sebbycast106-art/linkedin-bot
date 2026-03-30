import os
import json
from unittest.mock import patch
from job_archive_service import archive_description, get_archived_description, get_all_archived


def test_archive_and_retrieve(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    archive_description("123", "SWE Intern", "Citadel", "https://linkedin.com/jobs/view/123", "Build systems")
    assert get_archived_description("123") == "Build systems"


def test_dedup_by_job_id(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    archive_description("123", "SWE Intern", "Citadel", "url1", "desc1")
    archive_description("123", "SWE Intern", "Citadel", "url1", "desc2")
    entries = get_all_archived()
    assert len(entries) == 1
    assert entries[0]["description"] == "desc1"


def test_get_archived_description_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert get_archived_description("nonexistent") is None


def test_cap_at_200(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for i in range(210):
        archive_description(str(i), f"Job {i}", "Co", "url", f"desc {i}")
    entries = get_all_archived()
    assert len(entries) == 200


def test_get_all_archived_sorted_desc(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    archive_description("a", "First", "Co", "url", "desc a")
    archive_description("b", "Second", "Co", "url", "desc b")
    archive_description("c", "Third", "Co", "url", "desc c")
    entries = get_all_archived()
    assert len(entries) == 3
    # Most recent should be first
    assert entries[0]["job_id"] == "c"
    assert entries[-1]["job_id"] == "a"


def test_description_truncated_at_3000(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    long_desc = "x" * 5000
    archive_description("123", "Job", "Co", "url", long_desc)
    assert len(get_archived_description("123")) == 3000

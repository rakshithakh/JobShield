from app.services.job_relevance import looks_like_job_posting
from tests.conftest import SCAM_TEXT


def test_example_domain_content_is_not_a_job_posting():
    text = "Example Domain. This domain is for use in documentation examples without needing permission."
    assert not looks_like_job_posting(text)


def test_job_description_with_role_and_details_is_relevant():
    text = ("Senior Backend Engineer. We are hiring for this position. Requirements include five years of experience. "
            "Salary depends on experience. Apply through our careers page.")
    assert looks_like_job_posting(text)


def test_existing_scam_posting_fixture_is_still_relevant():
    assert looks_like_job_posting(SCAM_TEXT)

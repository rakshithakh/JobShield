"""Conservative content check for URL inputs before assigning a scam-risk score."""
import re

_JOB_CONTEXT = re.compile(
    r"\b(?:job|career|vacanc\w*|hiring|recruit\w*|employment|position|role|offer|placement|"
    r"engineer|developer|intern|analyst|manager|designer|technician|accountant)\b",
    re.I,
)
_JOB_DETAILS = re.compile(
    r"\b(?:salary|stipend|compensation|responsibilities|requirements?|qualifications?|experience|"
    r"interviews?|skills?|benefits|apply|application|candidate|applicant|resume|cv)\b",
    re.I,
)


def looks_like_job_posting(text: str) -> bool:
    """Accept URL content only when it has both job-context and job-detail language."""
    return bool(_JOB_CONTEXT.search(text) and _JOB_DETAILS.search(text))

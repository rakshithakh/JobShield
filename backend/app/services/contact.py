"""Contact-email analysis. The single place where personal-email contact is scored."""
import re

from .types import Signal

FREE_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.in", "yahoo.co.in", "hotmail.com", "hotmail.in",
    "outlook.com", "live.com", "rediffmail.com", "ymail.com", "aol.com", "icloud.com", "proton.me", "protonmail.com",
}
_EMAIL = re.compile(r"[\w.\-+]+@([\w\-]+(?:\.[\w\-]+)+)", re.I)
_FREE_MAIL_CONTACT_MENTION = re.compile(
    r"\b(?:send|email|contact|submit|share)\b.{0,100}\b(?:gmail|googlemail)"
    r"(?:\s+(?:email\s+)?(?:address|account|mailbox))?\b",
    re.I,
)
PERSONAL_EMAIL_POINTS = 25
FREE_MAIL_MENTION_POINTS = 10


def extract_emails(text: str) -> list[tuple[str, str]]:
    """[(full_email, domain)] with domains lower-cased, trailing punctuation removed."""
    out = []
    for m in _EMAIL.finditer(text):
        domain = m.group(1).lower().rstrip(".")
        out.append((m.group(0).rstrip(".").lower(), domain))
    return out


def is_free_domain(domain: str) -> bool:
    return domain in FREE_DOMAINS


def analyze_contact(text: str, company_is_known_employer: bool, company_name: str = "") -> list[Signal]:
    emails = extract_emails(text)
    if not emails:
        mention = _FREE_MAIL_CONTACT_MENTION.search(text)
        if mention:
            return [Signal(
                "contact:free_email_mentioned", "contact", "Free Email Contact Mentioned", "low",
                FREE_MAIL_MENTION_POINTS,
                "The posting directs applicants to a Gmail contact but gives no address to verify. Confirm the role through the employer's official careers site.",
                mention.group(0).strip(),
            )]
        return [Signal("contact:none", "contact", "No contact email in the text", "info", 0,
                       "Many genuine postings direct you to a careers portal instead, so this alone is not scored.")]
    signals: list[Signal] = []
    free = [e for e in emails if is_free_domain(e[1])]
    if free:
        known_employer_context = company_is_known_employer
        explanation = "Established employers normally email candidates from their own domain, not a free mailbox."
        if known_employer_context:
            explanation += " The company name matches a known employer, but this does not verify who controls the mailbox."
        signals.append(Signal(
            "contact:personal_email", "contact", "Personal Email Contact", "high" if known_employer_context else "medium",
            PERSONAL_EMAIL_POINTS, explanation, free[0][0]))
    else:
        domain = emails[0][1]
        slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
        dom = re.sub(r"[^a-z0-9]", "", domain)
        if slug and slug not in dom:
            signals.append(Signal("contact:domain_mismatch", "contact", "Contact domain differs from company name", "info", 0,
                                  f"The contact domain '{domain}' does not contain the company name. This is only informational; "
                                  "a custom domain is not proof of legitimacy and is not scored.", emails[0][0]))
        else:
            signals.append(Signal("contact:company_domain", "contact", "Contact uses a non-free-mail domain", "info", 0,
                                  "A custom domain is expected for real employers but is easy to fake, so it does not lower the risk score.",
                                  emails[0][0]))
    return signals

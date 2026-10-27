"""Rule-based signal detection (regex).

Carried over from the original app's SCAM_PATTERNS with these changes (RULES_VERSION 16):
  * rules-3: patterns pruned using the EMSCAD data (see ml/evaluate.py): the generic "immediately / apply now" urgency
    pattern fired on ~15% of GENUINE postings, "free accommodation" and "multi-level" (buildings) were also common in genuine
    ads. Too-Good-To-Be-True weight reduced 20 -> 10 (no measurable lift). The India-specific fee/UPI/Telegram rules cannot be
    validated on EMSCAD (US/UK-centred) and remain expert heuristics.
  * Evidence snippets are returned for every hit.
  * Negation-aware for the fee category ("we never charge a registration fee" is not a fee demand).
  * "Personal Email Contact" moved to contact.py (it used to be scored twice: here and in the domain check).
  * A few patterns added for reworded advance-fee / messaging-app scams the original missed.
  * rules-4: requests for identity/financial documents through WhatsApp or Telegram are flagged only with a nearby
    no-interview, pre-offer, or rapid guaranteed-offer cue; this narrow India-focused condition is not validated on EMSCAD.
  * rules-5: an explicit hiring-fee demand gains one additional category only when paired with a no-interview and
    offer/selection claim; this narrow conjunction avoids increasing scores for any one cue alone.
  * rules-6: chat-based OTP/UPI-PIN requests receive stronger weight, and a short verification deadline tied to
    offer cancellation is treated as urgency; these credential-theft patterns are not validated on EMSCAD.
  * rules-7: recognize direct UPI payment wording and confirmed-placement/guaranteed-employment wording in the
    existing fee + no-interview corroboration; no single phrase is sufficient for the extra points.
  * rules-8: recognize "guarantee your job" wording as an offer claim in the same fee + no-interview corroboration.
  * rules-9: recognize "immediate selection" as a selection claim in the same fee + no-interview corroboration.
  * rules-10: support comma-formatted payment amounts and "guarantee your job" wording.
  * rules-11: detect sensitive identity/financial/OTP requests over chat or messaging before/during interview-skipping flows.
  * rules-12: recognize "without an interview" as interview-skipping for fee/selection corroboration.
  * rules-13: recognize "no exam or interview" and flag explicit OTP/UPI-PIN demands even when no chat app is named.
  * rules-14: recognize "no interview is required" and offer-letter language in fee + interview-skipping claims.
  * rules-15: detect required laptop/equipment purchases and selection that skips assessments.
  * rules-16: score contextual requests for sensitive identity/financial data once per posting: 35 points for
    premature identity/bank requests, and 60 for card photos/details or authentication secrets. Post-hire payroll
    collection and explicit safety advice are excluded; the category remains under the existing 70-point cap.
"""
import re

from .types import Signal

RULES_VERSION = "rules-16"

# category -> (points, severity, explanation, patterns)
CATEGORIES: dict[str, tuple[int, str, str, list[str]]] = {
    "Registration/Training Fee": (30, "high",
        "Legitimate employers do not charge candidates to be hired or require purchases through recruiting agents before joining.", [
        r"(registration\s*fee|training\s*fee|joining\s*fee|security\s*deposit|processing\s*fee|kit\s*fee)",
        r"pay\s*(rs\.?|inr|Ã¢â€šÂ¹)\.?\s*\d[\d,]*",
        r"(rs\.?|Ã¢â€šÂ¹)\s*\d+\s*(registration|fee|joining|deposit|charge)",
        r"pay\s+\d+\s*(before|to\s*get|for\s*joining)",
        r"(fee|deposit|charge)\s*(of|is|:)?\s*(rs\.?|Ã¢â€šÂ¹)\s*\d+",
        r"\b(send|transfer|deposit)\s+(rs\.?|inr|Ã¢â€šÂ¹)?\s*\d+\b.{0,40}\b(kit|slot|confirm|upi|register|activation)",
        r"\b(?:purchase|buy|pay\s+for)\b.{0,80}\b(?:mandatory\s+)?(?:laptop|computer|equipment|device)\s+(?:package|kit)\b",
    ]),
    "Urgency Tactics": (20, "medium",
        "Pressure to act immediately limits your time to verify the offer.", [
        r"(only\s+\d+\s+seats?|limited\s+seats?|seats?\s+left)",
        r"\burgent(ly)?\s+(hiring|requirement|vacanc\w+|opening\w*|recruitment)\b",
        r"\b(apply|register|join)\s+(now|today)\s+(to|and|before)\s+(get|secure|confirm|avoid)\b",
        r"(last\s+date\s+today|closing\s+soon|hurry|don.t\s+miss)",
        r"(limited\s+(time|positions?|slots?|openings?))",
        r"\bwithin\s+\d+\s*(?:minutes?|mins?)\b.{0,50}\b(?:or|otherwise)\b.{0,40}\b(?:offer|job|position)\b.{0,30}\b(?:cancelled|canceled|withdrawn?)\b",
    ]),
    "Unrealistic Promises": (20, "medium",
        "Guaranteed income or no requirements at all is atypical for genuine roles.", [
        r"(no\s+experience\s+(needed|required|necessary))",
        r"(anyone\s+can\s+apply|no\s+qualification\s+required)",
        r"(guaranteed\s+(income|salary|earning|payment))",
        r"(unlimited\s+(earning|income|money|opportunity))",
        r"(be\s+your\s+own\s+boss)",
    ]),
    "Suspicious Work Pattern": (20, "medium",
        "Pay-per-task, daily wallet payouts or chat-app-only contact are common in task and advance-fee scams.", [
        r"(work\s+(timing|time)\s*[:\-]?\s*24\s*/\s*7)",
        r"(work\s+any\s*time|anytime\s+work)",
        r"(daily\s+payment|payment\s+daily|pay\s+daily)",
        r"(upi|digital\s+wallet|paytm)\s*(payment|transfer)",
        r"\b(?:pay|send|deposit|transfer)\b.{0,60}\b(?:via|by|using|through)\s+upi\b",
        r"(per\s+entry|per\s+form|per\s+page)\s*(rs|Ã¢â€šÂ¹|\d)",
        r"(rs|Ã¢â€šÂ¹)\s*\d+\s*per\s*(entry|form|page)",
        r"\b(contact|message|text|dm|reach)\s+(us\s+)?(only\s+)?(on|via|through)\s+(telegram|whatsapp)\b",
        r"\bearn\s+(rs\.?|inr|Ã¢â€šÂ¹)?\s*\d[\d,]*\s*(daily|per\s+day|a\s+day)\b",
    ]),
    "MLM/Network Marketing": (30, "high",
        "Income that depends on recruiting others is a pyramid/MLM model, not employment.", [
        r"(network\s+marketing|\bmlm\b|multi[\s\-]?level\s+marketing|direct\s+selling\s+(business|opportunit\w+|job))",
        r"(refer\s+(friends?|others?|people).*earn)",
        r"(join\s+our\s+network|build\s+your\s+network)",
        r"(downline|upline|pyramid)",
    ]),
    "Too Good To Be True": (10, "low",
        "Extravagant perks or income claims are a common lure.", [
        r"(free\s+(laptop|mobile|phone|iphone)\s+(for|on|after|when|to)\b)",
        r"(car\s+after\s+(target|achieving|joining|level))",
        r"(foreign\s+trip|abroad\s+trip|international\s+tour)",
        r"(earn\s+(rs\.?|Ã¢â€šÂ¹)\s*[1-9]\s*lakh|1\s*lakh\s+per\s+month)",
    ]),
}

RULE_POINTS_CAP = 70  # same cap as the original app

_NEGATION = re.compile(r"\b(no|never|not|without|zero|don'?t|do\s+not|doesn'?t|does\s+not|won'?t|will\s+not|free\s+of)\b", re.I)
_NEGATABLE = {"Registration/Training Fee"}
_COMPILED = {c: [re.compile(p, re.I) for p in spec[3]] for c, spec in CATEGORIES.items()}
_SENSITIVE_REQUEST = re.compile(
    r"\b(?:send|share|provide|submit|upload|forward|give|disclose|attach|photograph|"
    r"must\s+(?:send|share|provide|submit)|(?:required|asked)\s+to\s+(?:send|share|provide|submit))\b",
    re.I,
)
_SENSITIVE_DOCUMENT = re.compile(
    r"\b(?:aadhaar|aadhar)(?:\s+(?:card|number|no\.?))?\b|\bpan(?:\s+card)?\b|"
    r"\bidentity\s+documents?\b|\bpassport\b|\bdriving\s+licen[cs]e\b|"
    r"\b(?:bank\s+account|bank|account)\s+(?:details?|number|no\.?|information)\b",
    re.I,
)
_CRITICAL_SECRET = re.compile(
    r"\b(?:otp|one[- ]time password|(?:upi\s+)?pin|cvv|cvc|passwords?|passcodes?|"
    r"debit\s+card\s+(?:photo|photograph|picture|image)|credit\s+card\s+(?:photo|photograph|picture|image)|"
    r"photo\s+of\s+(?:your\s+)?(?:debit|credit)\s+card|(?:debit|credit)\s+card\s+(?:details?|number))\b",
    re.I,
)
_EARLY_HIRING = re.compile(
    r"\b(?:before|prior\s+to)\s+(?:(?:scheduling|arranging|conducting)\s+)?(?:(?:the|your)\s+)?(?:an?\s+)?"
    r"(?:interview|assessment|screening|offer|offer\s+letter)\b|"
    r"\b(?:pre[- ]offer|before\s+(?:you\s+are\s+)?hired|before\s+(?:the\s+)?first\s+interview)\b|"
    r"\bno\s+(?:technical\s+)?(?:exam|interview)|\bwithout\s+(?:(?:a|an)\s+)?(?:technical\s+)?interview\b",
    re.I,
)
_POST_HIRE_PAYROLL = re.compile(
    r"\b(?:payroll|salary\s+(?:deposit|payment)|wage\s+payment)\b.{0,100}\b(?:after|once)\s+(?:you\s+are\s+)?(?:hired|employed|onboarded)\b|"
    r"\b(?:after|once)\s+(?:you\s+are\s+)?(?:hired|employed|onboarded)\b.{0,100}\b(?:payroll|bank\s+account|bank\s+details)\b",
    re.I,
)
_NO_INTERVIEW_OR_ASSESSMENT = re.compile(
    r"\bno\s+(?:technical\s+)?(?:exam|interview)(?:\s*(?:or|/)\s*(?:technical\s+)?(?:exam|interview))?(?:\s+(?:is\s+)?(?:required|needed|necessary|conducted))?\b|"
    r"\bno\s+(?:assessment|test|screening)(?:\s+(?:is\s+)?(?:required|needed|necessary|conducted))?\b|"
    r"\bwithout\s+(?:(?:a|an)\s+)?(?:technical\s+)?(?:interview|assessment|exam|test|screening)\b",
    re.I,
)
_OFFER_OR_SELECTION = re.compile(
    r"\b(?:congratulations|immediate\s+selection|direct\s+selection|selected\s+for|you\s+are\s+selected|"
    r"guaranteed\s+(?:job\s+)?offer|confirm\s+your\s+offer)\b|"
    r"\bbefore\s+receiving\s+(?:the\s+)?(?:formal\s+)?offer\s+letter\b|"
    r"\bguarantee(?:s|d)?\s+(?:(?:you|your)\s+)?(?:a\s+)?(?:job|position|employment)\b|"
    r"\bplacement\s+(?:is\s+)?confirmed\b|"
    r"\bguarante(?:es|ed)\s+(?:you\s+)?(?:employment|a\s+job|a\s+position|a\s+placement)\b",
    re.I,
)


def _is_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 40):start]
    # only look inside the same clause/sentence
    cut = max(prefix.rfind(ch) for ch in ".!?;\n") if prefix else -1
    return bool(_NEGATION.search(prefix[cut + 1:]))


def _snippet(text: str, start: int, end: int, pad: int = 35) -> tuple[str, tuple[int, int]]:
    """Excerpt around a match, trimmed to word boundaries, plus the (start, end) of the matched phrase inside it."""
    lo, hi = max(0, start - pad), min(len(text), end + pad)
    while 0 < lo < start and not text[lo - 1].isspace():
        lo += 1
    while end < hi < len(text) and not text[hi].isspace():
        hi -= 1

    def squash(t: str) -> str:
        return re.sub(r"\s+", " ", t)

    before, match, after = squash(text[lo:start]).lstrip(), squash(text[start:end]).strip()[:120], squash(text[end:hi]).rstrip()
    prefix, suffix = ("\u2026" if lo > 0 else ""), ("\u2026" if hi < len(text) else "")
    s0 = len(prefix) + len(before)
    return prefix + before + match + after + suffix, (s0, s0 + len(match))


def _sensitive_data_messaging_signal(text: str) -> Signal | None:
    """Return one strongest sensitive-data warning, excluding safety advice and routine post-hire payroll."""
    early_hiring = bool(_EARLY_HIRING.search(text))
    matches: list[tuple[int, int, int, str]] = []
    for sentence in re.finditer(r"[^.!?;\n]+", text):
        part = sentence.group()
        request = _SENSITIVE_REQUEST.search(part)
        if not request or _is_negated(text, sentence.start() + request.start()):
            continue
        critical = _CRITICAL_SECRET.search(part)
        if critical:
            matches.append((60, sentence.start() + request.start(), sentence.start() + critical.end(), "critical"))
            continue
        # Card-number/details requests are unsafe regardless of hiring stage. Ordinary identity and
        # bank details are scored only when requested before an interview or offer.
        sensitive = _SENSITIVE_DOCUMENT.search(part)
        if not sensitive:
            continue
        card_data = re.search(r"\b(?:debit|credit)\s+card\s+(?:details?|number)\b", part, re.I)
        if card_data:
            matches.append((60, sentence.start() + request.start(), sentence.start() + card_data.end(), "critical"))
        elif early_hiring and not _POST_HIRE_PAYROLL.search(text):
            matches.append((35, sentence.start() + request.start(), sentence.start() + sensitive.end(), "early"))
    if not matches:
        return None
    points, start, end, kind = max(matches, key=lambda item: item[0])
    evidence, span = _snippet(text, start, end, pad=100)
    detail = (
        "Recruiters should never request an OTP, PIN, CVV, password, or photo/details of a payment card."
        if kind == "critical" else
        "Requests for identity or bank details before an interview or offer are premature; verify the employer independently."
    )
    return Signal(
        code="rule:sensitive_data_request", source="rules",
        title="Sensitive Personal or Financial Information Requested", severity="high", points=points,
        explanation=detail, evidence=evidence, evidence_span=span,
    )


def _fee_no_interview_offer_signal(text: str, signals: list[Signal]) -> Signal | None:
    """Add corroboration when a hiring payment is paired with skipped checks and a selection/offer claim."""
    if "rule:registration_training_fee" not in {signal.code for signal in signals}:
        return None
    no_interview = _NO_INTERVIEW_OR_ASSESSMENT.search(text)
    offer = _OFFER_OR_SELECTION.search(text)
    if not no_interview or not offer:
        return None

    start, end = min(no_interview.start(), offer.start()), max(no_interview.end(), offer.end())
    evidence, span = _snippet(text, start, end, pad=35)
    return Signal(
        code="rule:fee_no_interview_offer",
        source="rules",
        title="Payment with Skipped Hiring Checks",
        severity="high",
        points=20,
        explanation=("An upfront hiring payment combined with selection that skips interviews or assessments is a strong scam warning."),
        evidence=evidence,
        evidence_span=span,
    )


def detect_rule_signals(text: str) -> list[Signal]:
    """Returns at most one signal per category (first non-negated match), so overlapping patterns inside a category are not summed."""
    signals: list[Signal] = []
    for category, (points, severity, why, _) in CATEGORIES.items():
        hit = None
        for rx in _COMPILED[category]:
            for m in rx.finditer(text):
                if category in _NEGATABLE and _is_negated(text, m.start()):
                    continue
                hit = m
                break
            if hit:
                break
        if hit:
            snippet, span = _snippet(text, hit.start(), hit.end())
            signals.append(Signal(
                code="rule:" + re.sub(r"[^a-z]+", "_", category.lower()).strip("_"),
                source="rules", title=category, severity=severity, points=points,
                explanation=why, evidence=snippet, evidence_span=span))
    sensitive_signal = _sensitive_data_messaging_signal(text)
    if sensitive_signal:
        signals.append(sensitive_signal)
    fee_offer_signal = _fee_no_interview_offer_signal(text, signals)
    if fee_offer_signal:
        signals.append(fee_offer_signal)
    return signals


def capped_rule_points(signals: list[Signal]) -> int:
    return min(sum(s.points for s in signals if s.source == "rules"), RULE_POINTS_CAP)

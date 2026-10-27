import httpx
import pytest

from app.services.company import Mca21Provider, match_known_employer, match_name_heuristic, verify_company
from app.services.contact import analyze_contact, extract_emails
from app.services.salary import analyze_salary, match_role, parse_salary
from tests.conftest import make_settings


# ---- contact
def test_personal_email_scored_once():
    sigs = analyze_contact("mail me at hr.jobs@gmail.com", False, "Acme")
    assert [s.points for s in sigs] == [25]


def test_impersonation_adds_when_known_employer_uses_free_mail():
    sigs = analyze_contact("send resume to infosys.hr@gmail.com", True, "Infosys")
    assert len(sigs) == 1 and sigs[0].code == "contact:personal_email"
    assert sum(s.points for s in sigs) == 25
    assert sigs[0].severity == "high" and "known employer" in sigs[0].explanation


def test_company_domain_not_rewarded():
    sigs = analyze_contact("hr@infosys.com", True, "Infosys")
    assert sum(s.points for s in sigs) == 0


def test_no_email_is_informational_only():
    sigs = analyze_contact("apply on our portal", False, "")
    assert sigs[0].severity == "info" and sigs[0].points == 0


def test_gmail_contact_instruction_without_address_gets_weak_warning():
    sigs = analyze_contact("Send your portfolio to our company Gmail address.", False, "Acme")
    assert len(sigs) == 1
    assert sigs[0].code == "contact:free_email_mentioned" and sigs[0].points == 10


def test_unrelated_gmail_mention_is_not_a_contact_warning():
    sigs = analyze_contact("Our engineers use Gmail for internal alerts. Apply through our careers portal.", False, "Acme")
    assert sigs[0].code == "contact:none" and sigs[0].points == 0


def test_email_trailing_punctuation():
    assert extract_emails("write to a@b.com.")[0][1] == "b.com"


# ---- salary
def test_parse_monthly_and_lpa():
    assert parse_salary("Earn Rs 45000 per month")[0] == 540000
    assert parse_salary("CTC 4.5 LPA")[0] == 450000
    assert parse_salary("25k per month")[0] == 300000
    assert parse_salary("competitive pay") is None


def test_salary_far_above_benchmark_flagged():
    sig = analyze_salary("Data Entry Operator", "data entry job earn Rs 90000 per month")[0]
    assert sig.points == 30 and "unsourced" in sig.explanation


def test_salary_in_range_does_not_reduce_score():
    sig = analyze_salary("Software Engineer", "software engineer CTC 6 LPA")[0]
    assert sig.points == 0


def test_role_match_prefers_title():
    assert match_role("Data Entry Operator", "we also need a software developer") == "data entry"


# ---- company
def test_known_employer_whole_token_match():
    assert match_known_employer("Infosys Limited")
    assert match_known_employer("Tata Consultancy Services Limited")
    assert match_known_employer("Microsoft India")
    assert match_known_employer("GE Vernova")
    assert match_known_employer("gevernova")


def test_ge_vernova_is_recognized_without_adding_risk_points():
    checks, status, _, signals = verify_company("gevernova", Mca21Provider(make_settings()))
    assert status == "known_employer"
    assert next(c for c in checks if c.provider == "trusted_list").status == "known_employer"
    assert signals == []


def test_substring_whitelist_defect_fixed():
    assert not match_known_employer("Ola Earn Fast Jobs")
    assert not match_known_employer("Sapphire Marketing")
    assert not match_known_employer("a")


def test_name_heuristic_is_weak_and_named():
    assert match_name_heuristic("Nexgen Solutions") == "nexgen"
    assert match_name_heuristic("Acme Widgets") is None


class StubRegistry:
    def __init__(self, check):
        self.check = check

    def lookup(self, name):
        return self.check


def mca(handler, key="k"):
    s = make_settings(mca_api_key=key)
    return Mca21Provider(s, httpx.Client(transport=httpx.MockTransport(handler)))


def test_mca_not_configured_is_not_a_success():
    check, path = Mca21Provider(make_settings()).lookup("Acme")
    assert check.status == "not_configured" and path.status == "not_configured"


def test_mca_resource_id_default_is_confirmed_resource():
    assert make_settings().mca_resource_id == "4dbe5667-7b6b-41d7-82af-211562424d9a"


@pytest.mark.parametrize("outcome", [
    httpx.Response(200, json={"records": [{"CompanyName": "Acme", "CompanyStatus": "Active"}]}),
    httpx.Response(200, json={"records": []}),
    httpx.Response(200, json={"records": [{"CompanyName": "Acme", "CompanyStatus": "Strike Off"}]}),
    httpx.Response(403),
    httpx.Response(429),
    httpx.Response(200, text="<html>not json"),
    httpx.Response(200, json=["unexpected"]),
    httpx.ConnectTimeout("mock timeout"),
])
def test_mca_does_not_request_or_interpret_unsupported_name_filter(outcome):
    """Regardless of a hypothetical response, an unsupported query cannot provide company evidence."""
    calls = []

    def mocked_http(request):
        calls.append(request)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    c, p = mca(mocked_http).lookup("Acme")
    assert c.status == "unavailable" and p.status == "unavailable"
    assert "not reliable company-name lookup" in c.summary
    assert calls == []


def test_mca_unsupported_lookup_adds_no_risk_points():
    checks, status, _, signals = verify_company("Ordinary Example Ltd", mca(lambda r: None))
    assert status == "unavailable"
    assert next(c for c in checks if c.provider == "mca21").status == "unavailable"
    assert signals == []


def test_unverifiable_company_adds_no_risk_points():
    checks, status, paths, signals = verify_company("Totally Unknown Pvt Ltd", Mca21Provider(make_settings()))
    assert signals == [] and status == "unknown"


def test_heuristic_name_adds_only_weak_points():
    _, status, _, signals = verify_company("Nexgen Solutions", Mca21Provider(make_settings()))
    assert status == "name_heuristic" and [s.points for s in signals] == [15]


def test_missing_company_name():
    _, status, _, signals = verify_company("", Mca21Provider(make_settings()))
    assert status == "not_provided" and signals == []

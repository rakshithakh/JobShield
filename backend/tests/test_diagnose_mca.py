import httpx
import pytest

from scripts.diagnose_mca import main, probe


@pytest.mark.parametrize(
    ("error", "expected", "message"),
    [
        (httpx.ReadTimeout("slow"), "ReadTimeout", "service may be slow or hung"),
        (httpx.ConnectTimeout("no route"), "ConnectTimeout", "network, proxy, or firewall"),
    ],
)
def test_timeout_kind_explains_where_request_stalled(error, expected, message):
    def handler(request):
        raise error

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe(client, "resource", "secret", {"limit": 1})

    assert result.kind == "timeout"
    assert expected in result.detail
    assert message in result.detail


def test_timeout_option_is_accepted_and_company_argument_remains_intact(capsys):
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        if len(seen) == 1:
            return httpx.Response(200, json={"records": [{"CompanyName": "ACME LIMITED"}]})
        return httpx.Response(200, json={"records": [{"CompanyName": "ACME LIMITED"}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        code = main(["--timeout", "42", "ACME LIMITED"], client=client, env={"MCA_API_KEY": "test-key"})

    assert code == 0
    assert seen[1]["filters[CompanyName]"] == "ACME LIMITED"
    assert "Live calls made: 2" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "-1", "301", "not-a-number"])
def test_invalid_timeout_is_rejected(value, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--timeout", value], env={"MCA_API_KEY": "test-key"})
    assert exc.value.code == 2
    assert "--timeout" in capsys.readouterr().err

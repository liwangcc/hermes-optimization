"""The cost estimate, and that a remote endpoint gets nothing before it is shown and accepted."""
import pytest

import calib_cost
import calib_run
from conftest import EVAL

REMOTE = ["--facts", str(EVAL / "facts.json"), "--embed-url", "https://embeddings.example.invalid/v1",
          "--embed-model", "text-embedding-3-small"]


@pytest.mark.parametrize("text, n", [("", 1), ("abcd", 1), ("abcde", 2), ("数据库", 3), ("数据库 abc", 4),
                                     ("后端用 FastAPI 框架", 5 + 3)])
def test_tokens_count_cjk_characters_and_quarter_the_rest(text, n):
    assert calib_cost.tokens(text) == n


def test_a_local_endpoint_is_free():
    assert calib_cost.estimate(["abcd"] * 10, "bge-m3", local=True) == {"tokens": 10, "usd": 0.0,
                                                                         "price": "local endpoint, free"}


def test_a_listed_model_is_priced_per_million_tokens():
    est = calib_cost.estimate(["数" * 1000] * 2, "text-embedding-3-small", local=False)
    assert est["tokens"] == 2000 and est["usd"] == pytest.approx(2000 * 0.02 / 1e6)
    assert calib_cost.estimate(["数" * 1000], "text-embedding-3-large", False)["usd"] == pytest.approx(1000 * 0.13 / 1e6)


def test_a_given_price_wins_and_an_unknown_model_says_so():
    assert calib_cost.estimate(["数" * 500], "some-model", False, price=1.0)["usd"] == pytest.approx(0.0005)
    unknown = calib_cost.estimate(["abcd"], "some-model", False)
    assert unknown["usd"] is None and "--price-per-mtok" in unknown["price"]
    assert "price unknown" in calib_cost.line(1, unknown)


def test_a_remote_run_prints_the_estimate_and_sends_nothing_without_yes(v, tmp_path, capsys):
    assert calib_run.main([*REMOTE, "--out", str(tmp_path / "run")]) is None
    out = capsys.readouterr().out
    assert "estimate:" in out and "USD per 1M tokens (list price checked 2026-11)" in out and "nothing was sent" in out
    assert "example.invalid" not in out  # the address is never printed
    assert not (tmp_path / "run").exists()


def test_with_yes_a_missing_key_stops_before_anything_is_sent(v, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("CALIB_TEST_KEY", raising=False)
    with pytest.raises(SystemExit, match="CALIB_TEST_KEY is not set"):
        calib_run.main([*REMOTE, "--embed-key-env", "CALIB_TEST_KEY", "--yes", "--out", str(tmp_path / "run")])
    assert not (tmp_path / "run").exists()


def test_no_endpoint_and_no_stub_is_refused(v, tmp_path):
    with pytest.raises(SystemExit, match="EMBED_URL"):
        calib_run.main(["--facts", str(EVAL / "facts.json"), "--out", str(tmp_path / "run")])


def test_plain_http_to_a_public_host_is_refused_before_the_estimate(v, tmp_path, capsys):
    with pytest.raises(SystemExit, match="use https"):
        calib_run.main(["--facts", str(EVAL / "facts.json"), "--embed-url", "http://embeddings.example.invalid/v1",
                        "--embed-model", "m", "--out", str(tmp_path / "run")])
    assert "estimate" not in capsys.readouterr().out

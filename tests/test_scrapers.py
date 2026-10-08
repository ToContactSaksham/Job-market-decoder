import json
from pathlib import Path

from jmd.scrapers import arbeitnow, greenhouse, hn_hiring, jobicy, lever, remoteok, remotive
from jmd.scrapers.base import is_data_role, strip_html

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text())


def test_strip_html_keeps_line_breaks():
    txt = strip_html("<p>Hello <b>world</b></p><ul><li>a</li><li>b</li></ul>")
    assert "Hello world" in txt and "\na" in txt and "<" not in txt


def test_is_data_role():
    assert is_data_role("Senior Data Scientist") and is_data_role("BI Developer") and is_data_role("Analytics Engineer")
    assert not is_data_role("Frontend Developer") and not is_data_role("Nurse")


def test_remoteok_parse_filters_and_maps():
    posts = remoteok.parse(load("remoteok.json"))
    assert [p.title for p in posts] == ["Senior Data Scientist"]
    p = posts[0]
    assert p.id == "remoteok:100001" and p.salary_min == 150000 and p.salary_currency == "USD" and p.posted_at == "2026-09-01"
    assert "PyTorch" in p.description and "<" not in p.description and p.remote


def test_arbeitnow_parse():
    posts = arbeitnow.parse(load("arbeitnow.json"))
    assert len(posts) == 1 and posts[0].company == "Zalando" and posts[0].location == "Berlin" and posts[0].posted_at == "2025-09-03"


def test_remotive_parse_puts_salary_in_text():
    posts = remotive.parse(load("remotive.json"))
    assert len(posts) == 1 and posts[0].description.startswith("Salary: $70k - $90k")


def test_jobicy_parse_salary_fields():
    p = jobicy.parse(load("jobicy.json"))[0]
    assert p.salary_min == 160000 and p.salary_max == 200000 and p.salary_period == "year" and "Senior" in p.tags


def test_greenhouse_parse_unescapes_content():
    posts = greenhouse.parse(load("greenhouse.json"), "acme")
    assert len(posts) == 1 and posts[0].location == "New York, NY" and "Kafka" in posts[0].description and "&lt;" not in posts[0].description
    assert posts[0].company == "Acme" and posts[0].tags == ["Data Platform"]


def test_lever_parse_salary_range_and_lists():
    p = lever.parse(load("lever.json"), "figma")[0]
    assert p.salary_currency == "GBP" and p.salary_period == "year" and p.salary_min == 70000
    assert "Requirements" in p.description and "SQL" in p.description and p.location == "London, UK"


def test_hn_parse_pipe_header():
    posts = hn_hiring.parse_comments(load("hn.json"), "Who is hiring (September 2026)")
    assert len(posts) == 1
    p = posts[0]
    assert p.company == "Acme Corp" and p.title == "Senior Data Engineer" and p.remote and "$170k-$210k" in p.description

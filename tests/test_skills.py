import pandas as pd

from jmd.skills import SkillExtractor, discover_candidates, load_taxonomy


def test_taxonomy_loads_and_names_unique():
    skills = load_taxonomy()
    names = [s.name for s in skills]
    assert len(names) == len(set(names)) and len(names) > 80


def test_extract_aliases_and_guards():
    ex = SkillExtractor()
    got = set(ex.extract("Experience with Python, R, and SQL. Familiar with PySpark and sklearn. Power BI dashboards."))
    assert {"Python", "R", "SQL", "Spark", "scikit-learn", "Power BI", "Data Visualization"} <= got
    got = set(ex.extract("Go-to person who will go the extra mile. Sas is not SAS. We use Go and Rust. R&D team. HR reports."))
    assert "Go" in got and "SAS" in got and "R" not in got
    got = set(ex.extract("Deploy with Docker on k8s via Terraform. GenAI with LangChain, RAG and Hugging Face."))
    assert {"Docker", "Kubernetes", "Terraform", "LLMs", "Hugging Face"} <= got
    assert "Java" in ex.extract("Java") and "Java" not in ex.extract("JavaScript only")


def test_matrix_shape_and_dtype():
    ex = SkillExtractor()
    X = ex.matrix(pd.Series(["Python and SQL", "nothing", "Tableau"]))
    assert X.shape == (3, len(ex.names)) and X.dtypes.eq(bool).all()
    assert X.loc[0, "Python"] and X.loc[0, "SQL"] and not X.loc[1].any() and X.loc[2, "Tableau"]


def test_requirement_strength():
    ex = SkillExtractor()
    s = ex.requirement_strength("Requirements:\n- Python\n- SQL\nNice to have:\n- Spark\n- Airflow")
    assert s["Python"] == "required" and s["Spark"] == "nice-to-have"


def test_discover_skips_known_and_sentence_starts():
    ex = SkillExtractor()
    texts = pd.Series(["We use Python and Databricks. Experience with Foobar required. Also ClickHouse and Foobar."] * 25)
    cands = discover_candidates(texts, ex, min_docs=5)
    names = set(cands["candidate"])
    assert "Foobar" in names and "ClickHouse" in names
    assert "Python" not in names and "Databricks" not in names and "Experience" not in names

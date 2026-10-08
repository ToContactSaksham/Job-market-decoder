"""Synthetic demo corpus.

The live scrapers need network access to job boards. When that is not available
(CI, sandboxes, offline work) this module generates a corpus with the SAME
schema so the whole pipeline can run end to end. The generator is a simple,
explicit model of the job market:

    salary = base(role) * seniority * city * company_size * prod(skill premium) * noise

with skills drawn conditional on role family and with built-in co-occurrence
structure. Because the generative model is known, it doubles as a test oracle:
the analysis should recover the premiums and co-occurrence patterns encoded here.

Everything produced here is clearly tagged source="synthetic". Never mix it
with live data in a published analysis.
"""
from __future__ import annotations

import random
import uuid
from datetime import date, timedelta

from .schema import JobPosting

# ----------------------------------------------------------------------------
# Market model
# ----------------------------------------------------------------------------
ROLES = {  # role: (share, base salary USD)
    "Data Analyst": (0.30, 78_000),
    "Data Scientist": (0.25, 118_000),
    "Data Engineer": (0.20, 122_000),
    "ML Engineer": (0.12, 140_000),
    "Analytics Engineer": (0.06, 115_000),
    "BI Developer": (0.04, 92_000),
    "Data Manager": (0.03, 165_000),
}
SENIORITY = {"Junior": (0.18, 0.75), "": (0.42, 1.0), "Senior": (0.30, 1.28), "Staff": (0.06, 1.55), "Lead": (0.04, 1.45)}

CITIES = {  # city: (share, salary multiplier, country)
    "Remote": (0.28, 1.00, "US"), "San Francisco, CA": (0.11, 1.30, "US"), "New York, NY": (0.12, 1.22, "US"),
    "Seattle, WA": (0.06, 1.18, "US"), "Austin, TX": (0.05, 1.02, "US"), "Chicago, IL": (0.05, 1.00, "US"),
    "Boston, MA": (0.04, 1.12, "US"), "Los Angeles, CA": (0.04, 1.10, "US"), "Denver, CO": (0.03, 0.98, "US"),
    "Atlanta, GA": (0.03, 0.94, "US"), "Dallas, TX": (0.03, 0.96, "US"), "Washington, DC": (0.03, 1.08, "US"),
    "London, UK": (0.05, 0.80, "UK"), "Berlin, Germany": (0.03, 0.70, "DE"), "Toronto, Canada": (0.03, 0.78, "CA"),
    "Bangalore, India": (0.02, 0.25, "IN"),
}
SIZES = {"1-50": (0.17, 0.90), "51-200": (0.23, 0.96), "201-1000": (0.25, 1.00), "1001-5000": (0.18, 1.05), "5000+": (0.17, 1.12)}

# P(skill | role). Skills absent from a role dict get the "default" rate.
SKILL_RATES = {
    "default": {"SQL": .55, "Python": .50, "Excel": .20, "Communication": .45, "Stakeholder Management": .35, "Git": .25,
                "Statistics": .30, "Data Visualization": .35, "Agile": .15, "AWS": .25, "Jupyter": .10, "APIs": .18},
    "Data Analyst": {"SQL": .88, "Excel": .62, "Tableau": .42, "Power BI": .38, "Python": .48, "R": .14, "Statistics": .40,
                     "A/B Testing": .20, "Looker": .14, "Data Visualization": .60, "Google Analytics": .16, "dbt": .08,
                     "Metrics & KPIs": .35, "Product Analytics": .22, "Marketing Analytics": .14, "Snowflake": .14,
                     "BigQuery": .12, "Machine Learning": .12, "Alteryx": .06, "SQL Server": .12, "Communication": .62},
    "Data Scientist": {"Python": .92, "SQL": .78, "R": .28, "Machine Learning": .85, "Statistics": .70, "A/B Testing": .38,
                       "scikit-learn": .35, "pandas": .40, "Deep Learning": .30, "TensorFlow": .22, "PyTorch": .28,
                       "NLP": .22, "LLMs": .24, "Causal Inference": .18, "Bayesian": .10, "Spark": .30, "AWS": .40,
                       "GCP": .18, "Azure": .16, "Tableau": .18, "XGBoost": .20, "Time Series": .16, "Jupyter": .25,
                       "Docker": .20, "MLOps": .15, "Computer Vision": .10, "Recommender Systems": .10, "Git": .40,
                       "Data Visualization": .40, "Databricks": .14, "Snowflake": .14},
    "Data Engineer": {"Python": .85, "SQL": .88, "Spark": .60, "Airflow": .48, "Kafka": .30, "AWS": .58, "Azure": .28,
                      "GCP": .25, "Snowflake": .38, "Databricks": .30, "dbt": .32, "ETL": .70, "Data Warehousing": .55,
                      "Scala": .18, "Java": .20, "Docker": .40, "Kubernetes": .28, "Terraform": .22, "CI/CD": .35,
                      "Git": .50, "PostgreSQL": .35, "Hadoop": .18, "Redshift": .22, "BigQuery": .22, "Data Modeling": .40,
                      "Data Quality": .30, "Data Governance": .15, "Flink": .06, "Bash": .30, "NoSQL": .18, "MongoDB": .12,
                      "Fivetran": .10, "Prefect": .06, "Software Engineering": .35},
    "ML Engineer": {"Python": .95, "SQL": .55, "Machine Learning": .92, "Deep Learning": .60, "PyTorch": .62, "TensorFlow": .40,
                    "MLOps": .55, "Docker": .60, "Kubernetes": .45, "AWS": .55, "GCP": .30, "Azure": .22, "LLMs": .45,
                    "NLP": .30, "Computer Vision": .22, "Spark": .30, "scikit-learn": .35, "Hugging Face": .22,
                    "CI/CD": .40, "Git": .55, "Software Engineering": .55, "Recommender Systems": .15, "FastAPI": .25,
                    "Terraform": .15, "Databricks": .14, "Airflow": .25, "Reinforcement Learning": .06, "Statistics": .35,
                    "C++": .10, "Go": .06, "Bash": .30},
    "Analytics Engineer": {"SQL": .95, "dbt": .80, "Snowflake": .50, "BigQuery": .35, "Python": .60, "Looker": .40,
                           "Airflow": .35, "Data Modeling": .70, "Data Warehousing": .50, "Git": .55, "Tableau": .25,
                           "Fivetran": .25, "Data Quality": .40, "Metrics & KPIs": .40, "Redshift": .15, "Databricks": .12,
                           "CI/CD": .30, "Statistics": .20},
    "BI Developer": {"SQL": .92, "Power BI": .65, "Tableau": .50, "SQL Server": .45, "Data Modeling": .55, "Excel": .45,
                     "Data Warehousing": .45, "ETL": .45, "Azure": .35, "Python": .30, "Looker": .15, "Data Visualization": .70,
                     "Metabase": .10, "Alteryx": .10, "Snowflake": .20, "Oracle": .15},
    "Data Manager": {"SQL": .60, "Python": .50, "Stakeholder Management": .80, "Communication": .80, "Data Governance": .40,
                     "Machine Learning": .40, "Agile": .35, "Tableau": .30, "AWS": .30, "Snowflake": .25, "Statistics": .35,
                     "A/B Testing": .25, "Metrics & KPIs": .45, "Data Warehousing": .30},
}

# Co-occurrence structure: if `a` is present, P(b) is multiplied by factor.
COOCCUR = [("Spark", "Scala", 2.5), ("Airflow", "Python", 1.3), ("dbt", "Snowflake", 2.2), ("dbt", "BigQuery", 1.6),
           ("Kubernetes", "Docker", 2.5), ("Terraform", "AWS", 1.8), ("PyTorch", "Deep Learning", 2.0),
           ("LLMs", "Hugging Face", 3.0), ("LLMs", "NLP", 2.0), ("Causal Inference", "A/B Testing", 2.0),
           ("Causal Inference", "Statistics", 1.6), ("Power BI", "SQL Server", 1.8), ("Power BI", "Azure", 1.5),
           ("Looker", "BigQuery", 1.8), ("Kafka", "Flink", 4.0), ("Hadoop", "Hive", 1.0), ("Bayesian", "Statistics", 1.5),
           ("MLOps", "Docker", 1.8), ("Databricks", "Spark", 2.5), ("Tableau", "Excel", 1.3)]

# "True" salary premiums encoded in the demo market (multiplicative).
PREMIUM = {"Spark": 1.06, "Kafka": 1.06, "Airflow": 1.03, "Kubernetes": 1.07, "Terraform": 1.04, "Scala": 1.07,
           "Machine Learning": 1.05, "Deep Learning": 1.07, "PyTorch": 1.06, "LLMs": 1.12, "Hugging Face": 1.05,
           "MLOps": 1.08, "Causal Inference": 1.10, "Bayesian": 1.06, "A/B Testing": 1.04, "Reinforcement Learning": 1.12,
           "Computer Vision": 1.05, "Recommender Systems": 1.07, "Snowflake": 1.03, "dbt": 1.04, "Databricks": 1.05,
           "AWS": 1.04, "GCP": 1.04, "Go": 1.05, "C++": 1.06, "Flink": 1.09, "Rust": 1.0,
           "Excel": 0.93, "Power BI": 0.95, "Tableau": 0.99, "SQL Server": 0.96, "Alteryx": 0.97, "Google Analytics": 0.96,
           "Stakeholder Management": 1.02, "Data Governance": 1.03, "Software Engineering": 1.04}

# Demand trend over the sampled year: multiplier at the END of the window vs the start.
TREND = {"LLMs": 2.4, "Hugging Face": 2.0, "MLOps": 1.5, "dbt": 1.4, "Snowflake": 1.25, "Databricks": 1.3,
         "Hadoop": 0.55, "SAS": 0.6, "Alteryx": 0.8, "Excel": 0.9, "Causal Inference": 1.3, "Kafka": 1.1}

# City/size demand tilts: multiply P(skill) in a given city or size bucket.
CITY_TILT = {"San Francisco, CA": {"LLMs": 1.7, "PyTorch": 1.4, "MLOps": 1.4, "Excel": 0.6, "Power BI": 0.5},
             "New York, NY": {"A/B Testing": 1.3, "Causal Inference": 1.4, "Finance Domain": 2.5, "Excel": 1.2},
             "Seattle, WA": {"AWS": 1.5, "Spark": 1.3, "Scala": 1.4},
             "Chicago, IL": {"SQL Server": 1.4, "Power BI": 1.4, "Supply Chain": 2.0},
             "Austin, TX": {"Power BI": 1.3, "Tableau": 1.2},
             "Boston, MA": {"Healthcare Domain": 2.5, "R": 1.6, "Bayesian": 1.5},
             "Washington, DC": {"Privacy & Compliance": 2.0, "Tableau": 1.3, "R": 1.3},
             "London, UK": {"Finance Domain": 2.0, "GCP": 1.3, "Looker": 1.3},
             "Berlin, Germany": {"GCP": 1.4, "Kafka": 1.4, "Privacy & Compliance": 1.6},
             "Bangalore, India": {"Azure": 1.5, "Power BI": 1.4, "Hadoop": 1.5},
             "Remote": {"dbt": 1.2, "Snowflake": 1.1, "Communication": 1.2}}
SIZE_TILT = {"1-50": {"dbt": 1.5, "LLMs": 1.5, "Software Engineering": 1.3, "Data Governance": 0.4, "SAS": 0.2, "Hadoop": 0.3, "Metabase": 2.0},
             "51-200": {"dbt": 1.3, "Snowflake": 1.2, "Metabase": 1.5, "Data Governance": 0.6},
             "201-1000": {},
             "1001-5000": {"Airflow": 1.2, "Data Governance": 1.4, "Agile": 1.3},
             "5000+": {"Hadoop": 2.0, "SAS": 2.5, "Data Governance": 2.0, "Privacy & Compliance": 1.6, "Scala": 1.3,
                       "Agile": 1.5, "Oracle": 2.0, "SQL Server": 1.4, "Excel": 1.2, "dbt": 0.6}}

DOMAIN_SKILLS = ["Finance Domain", "Healthcare Domain", "Marketing Analytics", "Supply Chain", "Product Analytics", "Privacy & Compliance"]

# ----------------------------------------------------------------------------
# Text generation: skills are mentioned via varied surface forms so that the
# extractor is tested against realistic aliases.
# ----------------------------------------------------------------------------
SURFACE = {
    "Python": ["Python", "Python 3", "python"], "SQL": ["SQL", "advanced SQL", "T-SQL"], "R": ["R", "R/Python", "R (tidyverse)"],
    "Spark": ["Spark", "PySpark", "Apache Spark"], "scikit-learn": ["scikit-learn", "sklearn"], "pandas": ["pandas", "pandas/numpy"],
    "Power BI": ["Power BI", "PowerBI"], "AWS": ["AWS", "AWS (S3, EMR, Redshift)", "Amazon Web Services"],
    "GCP": ["GCP", "Google Cloud", "GCP (BigQuery, Vertex AI)"], "Kubernetes": ["Kubernetes", "k8s"],
    "Machine Learning": ["machine learning", "ML", "predictive modeling"], "LLMs": ["LLMs", "large language models", "GenAI", "generative AI (RAG, LangChain)"],
    "Deep Learning": ["deep learning", "neural networks"], "ETL": ["ETL", "ELT", "data pipelines"],
    "Data Warehousing": ["data warehousing", "data lake", "star schema"], "A/B Testing": ["A/B testing", "experimentation"],
    "Causal Inference": ["causal inference", "uplift modeling"], "CI/CD": ["CI/CD", "GitHub Actions", "Jenkins"],
    "Git": ["Git", "GitHub"], "Data Visualization": ["data visualization", "dashboards", "matplotlib/seaborn"],
    "Excel": ["Excel", "advanced Excel (pivot tables, VLOOKUP)", "spreadsheets"], "MLOps": ["MLOps", "MLflow", "model deployment and monitoring"],
    "Statistics": ["statistics", "statistical analysis", "regression and hypothesis testing"], "Hadoop": ["Hadoop", "Hadoop/Hive"],
    "Bash": ["Linux", "bash scripting"], "XGBoost": ["XGBoost", "LightGBM"], "NLP": ["NLP", "natural language processing"],
    "Jupyter": ["Jupyter", "notebooks"], "APIs": ["REST APIs", "APIs"], "Docker": ["Docker", "containers"],
    "Stakeholder Management": ["stakeholders", "cross-functional partners"], "Communication": ["communication skills", "storytelling with data"],
    "Metrics & KPIs": ["KPIs", "north star metrics"], "Software Engineering": ["software engineering best practices", "unit testing and code review"],
    "Time Series": ["time series forecasting", "forecasting"], "Data Modeling": ["data modeling", "semantic layer"],
    "Data Quality": ["data quality", "Great Expectations"], "Terraform": ["Terraform", "infrastructure as code"],
    "Hugging Face": ["Hugging Face"], "Finance Domain": ["financial services", "fintech"], "Healthcare Domain": ["healthcare", "clinical data"],
    "Marketing Analytics": ["marketing analytics", "customer segmentation and churn"], "Supply Chain": ["supply chain", "logistics"],
    "Product Analytics": ["product analytics", "funnel and retention analysis"], "Privacy & Compliance": ["GDPR", "HIPAA"],
    "Agile": ["Agile", "Scrum/Jira"], "FastAPI": ["FastAPI", "Flask"], "Bayesian": ["Bayesian methods", "PyMC"],
    "Recommender Systems": ["recommender systems", "personalization"], "Computer Vision": ["computer vision", "OpenCV"],
    "Reinforcement Learning": ["reinforcement learning"], "SQL Server": ["SQL Server", "SSIS/SSRS"], "Metabase": ["Metabase", "Superset"],
    "Google Analytics": ["Google Analytics", "GA4"], "Fivetran": ["Fivetran"], "Prefect": ["Prefect", "Dagster"], "Flink": ["Flink"],
}

INTRO = [
    "{company} is a {size_desc} company building {product}. We are hiring a {title} to join our {team} team in {location}.",
    "About the role: as a {title} at {company} you will {mission}.",
    "{company} ({size_desc}) is looking for a {title}. This role sits in the {team} team and reports to the {boss}.",
    "We're {company}, a {size_desc} {industry} company. Our {team} team is growing and we need a {title} who can {mission}.",
]
PRODUCTS = ["analytics software", "a consumer marketplace", "payments infrastructure", "a healthcare platform", "logistics tooling",
            "an ad-tech platform", "developer tools", "a fintech app", "an e-commerce brand", "industrial IoT products"]
INDUSTRY = ["SaaS", "fintech", "healthtech", "retail", "media", "logistics", "insurance", "gaming", "ed-tech", "energy"]
TEAMS = ["Analytics", "Data Platform", "Growth", "Product", "Finance", "Marketing", "Risk", "Core ML", "Insights", "Operations"]
BOSSES = ["Head of Data", "Director of Analytics", "VP Engineering", "Chief Data Officer", "Analytics Manager"]
MISSIONS = ["turn raw data into decisions", "own our metrics layer end to end", "build and maintain reliable data pipelines",
            "ship models into production", "partner with product and finance leaders", "design experiments and measure impact"]
RESP = ["Build and maintain {s1} pipelines feeding our {s2} warehouse.", "Analyse user behaviour using {s1} and present findings to {s2}.",
        "Develop, validate and deploy models with {s1} and {s2}.", "Own dashboards in {s1} and define {s2} with business partners.",
        "Write production-quality {s1} code and review colleagues' work.", "Design experiments, run {s1}, and quantify impact.",
        "Partner with engineering to improve {s1} and {s2}."]
REQ_HEAD = ["Requirements", "What you bring", "You should have", "Minimum qualifications", "Skills & experience"]
REQ_LINE = ["{yrs}+ years of experience with {s}", "Strong proficiency in {s}", "Hands-on experience with {s}", "Expert-level {s}",
            "Working knowledge of {s}", "Experience building with {s} in production", "Comfortable using {s} day to day",
            "{s} (required)"]
NICE_HEAD = ["Nice to have", "Bonus points", "Preferred qualifications"]
BENEFITS = ["We offer equity, health insurance and a learning budget.", "Hybrid schedule: 2 days in the office.",
            "This is a fully remote position open to candidates in {country}.", "401(k) match, unlimited PTO and a home office stipend.",
            "We are an equal opportunity employer."]
SAL_FMT = ["The base salary range for this role is ${lo:,}-${hi:,} per year.", "Salary: ${lo_k}k - ${hi_k}k USD",
           "Compensation: ${lo:,} to ${hi:,} annually plus bonus.", "Base pay: ${lo_k}K–${hi_k}K"]
NOISE = ["Please note this position does not offer visa sponsorship.", "Applicants must be authorised to work in {country}.",
         "We review every application; expect to hear back within two weeks.", "Occasional travel (up to 10%) may be required.",
         "This role may require occasional on-call support.", "We go the extra mile for our customers."]

_NAME_A = ["North", "Blue", "Silver", "Bright", "Clear", "Iron", "Summit", "Harbor", "Vector", "Pioneer", "Granite", "Lumen", "Echo",
           "Apex", "Cobalt", "Juniper", "Meridian", "Orchid", "Quartz", "Sable", "Tundra", "Verdant", "Zephyr", "Atlas", "Beacon"]
_NAME_B = ["Analytics", "Labs", "Systems", "Data", "Health", "Logistics", "Finance", "Robotics", "Commerce", "Media", "Works", "Networks",
           "Cloud", "Insights", "Capital", "Markets", "Mobility", "Energy", "Games", "Learning"]


def _choice(rng: random.Random, table: dict) -> str:
    keys = list(table)
    return rng.choices(keys, weights=[table[k][0] for k in keys], k=1)[0]


def _companies(rng: random.Random, n: int) -> list[tuple[str, str, str]]:
    seen, out = set(), []
    while len(out) < n:
        name = f"{rng.choice(_NAME_A)}{rng.choice(_NAME_B)}" if rng.random() < .5 else f"{rng.choice(_NAME_A)} {rng.choice(_NAME_B)}"
        if name in seen:
            continue
        seen.add(name)
        out.append((name, _choice(rng, SIZES), rng.choice(INDUSTRY)))
    return out


def _skills_for(rng: random.Random, role: str, city: str, size: str, t: float) -> list[str]:
    rates = dict(SKILL_RATES["default"])
    rates.update(SKILL_RATES.get(role, {}))
    for d in DOMAIN_SKILLS:
        rates.setdefault(d, 0.08)
    present = []
    for skill, p in rates.items():
        p *= CITY_TILT.get(city, {}).get(skill, 1.0) * SIZE_TILT.get(size, {}).get(skill, 1.0)
        if skill in TREND:
            p *= TREND[skill] ** t  # t in [0,1] across the window
        if rng.random() < min(p, 0.98):
            present.append(skill)
    # second pass for co-occurrence boosts
    for a, b, factor in COOCCUR:
        if a in present and b not in present and b in rates:
            if rng.random() < min(rates[b] * (factor - 1), 0.9):
                present.append(b)
    return present


def _surface(rng: random.Random, skill: str) -> str:
    return rng.choice(SURFACE.get(skill, [skill]))


def _description(rng: random.Random, *, company, size, industry, title, location, skills, salary, country) -> str:
    size_desc = {"1-50": "seed-stage", "51-200": "fast-growing Series B", "201-1000": "mid-sized", "1001-5000": "large", "5000+": "Fortune-500 scale"}[size]
    core, nice = skills[:max(3, int(len(skills) * .7))], skills[max(3, int(len(skills) * .7)):]
    parts = [rng.choice(INTRO).format(company=company, size_desc=size_desc, product=rng.choice(PRODUCTS), title=title, team=rng.choice(TEAMS),
                                       location=location, mission=rng.choice(MISSIONS), boss=rng.choice(BOSSES), industry=industry)]
    parts.append("What you'll do:")
    for _ in range(rng.randint(3, 5)):
        s1, s2 = (rng.sample(core, 2) if len(core) >= 2 else (core[0], core[0]))
        parts.append("- " + rng.choice(RESP).format(s1=_surface(rng, s1), s2=_surface(rng, s2)))
    parts.append(rng.choice(REQ_HEAD) + ":")
    for s in core:
        parts.append("- " + rng.choice(REQ_LINE).format(s=_surface(rng, s), yrs=rng.choice([2, 3, 3, 4, 5, 5, 7])))
    if nice:
        parts.append(rng.choice(NICE_HEAD) + ":")
        parts.append("- Familiarity with " + ", ".join(_surface(rng, s) for s in nice))
    if salary:
        lo, hi = salary
        parts.append(rng.choice(SAL_FMT).format(lo=lo, hi=hi, lo_k=lo // 1000, hi_k=hi // 1000))
    parts.append(rng.choice(BENEFITS).format(country=country))
    parts.append(rng.choice(NOISE).format(country=country))
    return "\n".join(parts)


def generate(n: int = 4000, seed: int = 42, days: int = 365, as_of: date | None = None) -> list[JobPosting]:
    rng = random.Random(seed)
    as_of = as_of or date(2026, 10, 1)
    companies = _companies(rng, max(60, n // 12))
    out = []
    for i in range(n):
        role = _choice(rng, ROLES)
        sen = _choice(rng, SENIORITY)
        city = _choice(rng, CITIES)
        company, size, industry = rng.choice(companies)
        offset = rng.randint(0, days)
        posted = as_of - timedelta(days=offset)
        t = 1 - offset / days
        skills = _skills_for(rng, role, city, size, t)
        base = ROLES[role][1] * SENIORITY[sen][1] * CITIES[city][1] * SIZES[size][1]
        for s in skills:
            base *= PREMIUM.get(s, 1.0)
        mid = base * rng.lognormvariate(0, 0.12)
        has_salary = rng.random() < 0.55
        if has_salary:
            spread = rng.uniform(0.08, 0.22)
            lo, hi = int(round(mid * (1 - spread), -3)), int(round(mid * (1 + spread), -3))
        else:
            lo = hi = None
        title = f"{sen} {role}".strip()
        if rng.random() < .25:
            title += rng.choice([", Growth", " - Platform", " (Marketing)", " II", ", Risk", " - Remote"])
        remote = city == "Remote" or rng.random() < .15
        country = CITIES[city][2]
        put_salary_in_text = has_salary and rng.random() < 0.5
        desc = _description(rng, company=company, size=size, industry=industry, title=title, location=city, skills=skills,
                            salary=(lo, hi) if put_salary_in_text else None, country=country)
        out.append(JobPosting(
            id=f"synthetic:{uuid.UUID(int=rng.getrandbits(128))}",
            source="synthetic",
            url="",
            title=title,
            company=company,
            location=city if city != "Remote" else rng.choice(["Remote", "Remote - US", "Remote (Worldwide)", "USA (Remote)"]),
            remote=remote,
            posted_at=posted.isoformat(),
            salary_min=None if put_salary_in_text or not has_salary else float(lo),
            salary_max=None if put_salary_in_text or not has_salary else float(hi),
            salary_currency=None if put_salary_in_text or not has_salary else "USD",
            salary_period=None if put_salary_in_text or not has_salary else "year",
            company_size=size if rng.random() < 0.7 else None,  # some sources don't publish size
            description=desc,
            tags=[role.lower().replace(" ", "-"), industry.lower()],
        ))
    return out

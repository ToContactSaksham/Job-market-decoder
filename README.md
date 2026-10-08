# Job Market Decoder

Scrape thousands of job postings for data roles, extract skills with regex/NLP, and work out
**which skills pay more, which combinations are rare, and how demand shifts by city, company size
and time**. Ends with a *"what should I learn next?"* recommendation engine.

```
jmd scrape   ->  jmd build   ->  jmd analyze   ->  jmd recommend --have "SQL,Excel" --role "Data Analyst"
(7 job APIs)     (clean +        (report, 9        (ranked skills + learning path)
                  skills)         figures, tables)
```

> **Status of the shipped numbers.** The report and figures checked into `outputs/` were produced from the
> **synthetic demo corpus** (`jmd synth`), because the environment this was built in had no network
> route to job boards. The scrapers are real and unit-tested against recorded API shapes; run
> `jmd scrape` on a machine with internet access to replace the demo data with live postings.
> The demo corpus is generated from an explicit market model (see `jmd/synth.py`), which also makes
> it a test oracle: the analysis is checked to recover the premiums and demand tilts encoded in it.

## What's inside

| Stage | Module | What it does |
|---|---|---|
| Scrape | `jmd/scrapers/` | Adapters for **RemoteOK, Arbeitnow, Remotive, Jobicy, Greenhouse boards, Lever postings, HN "Who is hiring"**. All public JSON APIs, polite rate-limiting + retries, HTML stripped, one common schema (`jmd/schema.py`). |
| Demo data | `jmd/synth.py` | Generates a realistic corpus with the same schema when scraping is not possible (CI, offline). Skills, salaries, cities, company sizes and trends follow a documented generative model. |
| Clean | `jmd/clean.py` | Role family + seniority from the title, canonical city/country (`data/taxonomy/cities.csv`), remote flag, company-size bucket (published field → lookup table → text cues like *Series B* / *Fortune 500* / *2,000+ employees*), annual USD salary (structured fields or regex over the description; hourly/monthly annualised, currencies converted), de-duplication of cross-posted jobs. |
| Extract | `jmd/skills.py` + `data/taxonomy/skills.yaml` | 93 skills in 10 categories, ~290 regex patterns with aliases (PySpark → Spark, sklearn → scikit-learn, k8s → Kubernetes). Case-sensitive guards for short names (R, SAS, Go). Required vs nice-to-have classification by section header. `jmd discover` lists frequent terms **not** yet in the taxonomy so it can grow with the data. |
| Analyze | `jmd/analysis.py` | Demand shares; **adjusted salary premiums** (ridge regression of log salary on skill indicators + role, seniority, city, company size, remote, source; bootstrap CIs); co-occurrence lift; **rare-but-valuable pairs** scored on salary residuals; demand index by city and by company size; monthly demand trends with slope tests. |
| Recommend | `jmd/recommend.py` | Scores every skill you don't have on demand in your target segment, adjusted pay premium, adjacency to what you already know, and the share of postings you would newly qualify for; plus a greedy multi-step learning path. |
| Report | `jmd/report.py` | `outputs/report.md` with tables, 9 figures in `outputs/figures/`, CSV tables in `outputs/tables/`. |

## Quick start

```bash
pip install -r requirements.txt            # or: pip install -e .  (gives you the `jmd` command)

# A. Offline / demo: synthetic corpus -> full report in ~30 s
python -m jmd all --demo --n 4000

# B. Live: scrape the public APIs (needs internet), then build + analyze
python -m jmd scrape                       # all sources; or --sources remoteok,greenhouse --query airbnb,stripe
python -m jmd build --raw live
python -m jmd analyze

# Ask the recommender
python -m jmd recommend --have "SQL,Excel,Tableau" --role "Data Analyst" --city "New York" --path 4
python -m jmd recommend --have "python,sql,airflow,aws" --role "Data Engineer"

# Find terms the taxonomy is missing
python -m jmd discover --top 40

python -m pytest -q                        # tests
```

Example output:

```
Target: Data Analyst / New York (170 postings). You have: SQL, Excel, Tableau.
You already cover >=60% of the hard skills listed in 1.2% of postings (mean coverage 30%).

Learn next (ranked):
 1. Data Visualization   score 0.81 | asked for in 75% of target postings; +0.5% adjusted pay premium; unlocks 11.2% more postings
 2. Statistics           score 0.55 | asked for in 43% of target postings; +0.3% adjusted pay premium; unlocks 6.5% more postings
 3. Python               score 0.54 | asked for in 51% of target postings; -0.8% adjusted pay premium; unlocks 5.3% more postings
 4. Metrics & KPIs       score 0.50 | asked for in 38% of target postings; +1.8% adjusted pay premium; 1.5x more likely alongside skills you have
 5. A/B Testing          score 0.41 | asked for in 21% of target postings; +3.3% adjusted pay premium; unlocks 2.9% more postings
```

## The analysis, in pictures (demo data)

**Which skills pay more?** Raw "with vs. without" gaps mostly reflect *who* asks for a skill (ML engineers
earn more *and* ask for PyTorch). The adjusted premium holds role, seniority, city, company size and remote
constant:

![premiums](outputs/figures/02_skill_premiums.png)

![raw vs adjusted](outputs/figures/03_raw_vs_adjusted.png)

**How does demand shift by city and company size?** Index = share in segment / share overall.

![city](outputs/figures/05_city_demand_index.png)

![size](outputs/figures/06_company_size_demand_index.png)

**How is demand moving?**

![trends](outputs/figures/07_demand_trends.png)

**Which skills travel together?**

![cooccurrence](outputs/figures/04_cooccurrence_lift.png)

The full write-up with tables (rare combos, bundles, salary by role/city/size, rising/falling skills,
recommender examples) is in [`outputs/report.md`](outputs/report.md).

## Method notes

- **Salary premium model.** `log(salary_mid) ~ ridge(controls + 93 skill indicators)`. The coefficient of a
  skill is the log-difference between a posting listing it and an otherwise identical posting; reported as
  `exp(b) - 1`. 95% intervals come from 200 bootstrap resamples of postings. Only skills with ≥30 salaried
  postings are reported. On the demo market the model recovers the encoded premiums (e.g. LLMs +12%,
  Causal Inference +11%, Excel −7%) with R² ≈ 0.92.
- **Rare but valuable combos.** Pairs present in ≤3% of postings. Pay is measured on *residuals* of a
  controls-only model, so a pair does not score simply because it is typical of a well-paid role;
  `vs_either` compares against the better-paid of the two skills alone, with a t-statistic.
- **Demand by city / size.** Share of postings in the segment mentioning the skill, divided by the overall
  share; segments need ≥40 postings.
- **Trends.** Monthly share per skill; growth ratio of the last third of the window to the first third, and
  a linear slope with p-value. Needs ≥3 months with ≥50 postings each.
- **Recommender score.** `0.35·demand + 0.25·pay + 0.15·adjacency + 0.25·unlock + 0.1·rarity`, each signal
  min-max scaled across candidates. `unlock` = share of segment postings where you would cross 60% hard-skill
  coverage after adding the skill. Rarity rewards skills with a >3% premium and <15% demand. Weights are
  arguments to `Recommender(...)`.
- **Caveats.** Postings state ranges, not offers; salary coverage is typically 30–55%. Regex extraction
  misses skills phrased unusually and the taxonomy is opinionated. Company size is inferred for most
  sources. Synthetic data is only for exercising the pipeline; do not quote its numbers as market facts.

## Layout

```
jmd/                 package (cli, schema, config, clean, skills, analysis, recommend, report, synth, scrapers/)
data/taxonomy/       skills.yaml, cities.csv, company_sizes.csv
data/raw/live/       scraped CSVs (git-ignored)      data/raw/demo/   synthetic corpus
data/processed/      postings.csv + skills_matrix.csv (built)
outputs/             report.md, figures/, tables/
tests/               unit tests incl. recorded API fixtures and generative-truth checks
```

## Extending

- **Add a skill:** one line in `data/taxonomy/skills.yaml` (`Name: ['\bregex\b', ...]`; prefix a pattern with
  `(?-i)` for case-sensitive). Run `jmd discover` to see what the data suggests.
- **Add a source:** drop a module in `jmd/scrapers/` exposing `fetch(limit, query) -> list[JobPosting]` and
  register it in `jmd/scrapers/__init__.py`.
- **Add known companies' sizes:** `data/taxonomy/company_sizes.csv`.

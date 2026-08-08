# Grant Intelligence Platform

Grant Intelligence Platform helps EcoServants quickly identify and prioritize potential grant funders from IRS nonprofit data. It converts a large Business Master File (BMF) CSV into an explainable, ranked research list, reducing manual prospect-screening time.

## Key features

- Cleans IRS data by validating EINs and organization codes, standardizing names and states, handling missing values, and removing duplicates.
- Identifies likely 501(c)(3) grantmakers using foundation-related name keywords.
- Classifies prospects into Environment/Conservation, Youth/Education, Community Improvement, Public Benefit, or Other.
- Uses basic NLP with TF-IDF and cosine similarity to compare organization text with EcoServants' mission.
- Calculates a transparent score out of 100 using funder type, mission keywords, geography, NTEE alignment, financial codes, and mission similarity.
- Assigns High, Medium, or Low Priority and explains why each organization was selected.
- Provides searchable tables, filters, Plotly charts, and CSV export through Streamlit.

## Technology

Python, Pandas, scikit-learn, Plotly, Streamlit, and pytest.

## How it works

1. Upload an IRS BMF CSV or use the included sample data.
2. The pipeline cleans and filters the organizations.
3. Keyword rules and NLP evaluate mission alignment.
4. The scoring model ranks likely funders.
5. Users explore results in the dashboard and export filtered prospects.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run dashboard.py
```

Streamlit will display a local browser address, usually `http://localhost:8501`.

## Project structure

```text
classification.py
dashboard.py
data_processing.py
nlp_similarity.py
scoring.py
data/sample_bmf.csv
tests/test_pipeline.py
requirements.txt
```

## Limitations

The ranking supports grant research but does not confirm that a foundation is accepting applications or will provide funding. IRS records may be incomplete or outdated, and every recommended prospect should be verified through its website and recent Form 990 filings.

## License

MIT

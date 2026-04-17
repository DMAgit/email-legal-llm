# Contract Risk Analyzer

Email-driven contract risk analyzer foundation for a take-home style project.

The current milestone establishes the FastAPI app, typed settings, YAML model
configuration, logging, and core domain models. Later milestones add inbound
Mailgun ingestion, parsing, extraction, retrieval, classification, and
persistence.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` if you need to reset local defaults. The checked-in
`.env` contains only empty secret placeholders for this milestone.

## Run

```powershell
uvicorn app.main:app --reload
```

Then open:

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/model-configs`

## Tests

```powershell
python -m pytest
```

Runtime-only installs can use `requirements.txt`.

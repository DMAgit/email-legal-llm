# Contract Risk Analyzer

Email-driven contract risk analyzer foundation for a take-home style project.

The current milestone accepts inbound Mailgun-style email webhooks, stores
attachments locally, detects PDF/image/CSV files, and parses attachments into
normalized raw text and chunks. Later milestones add structured extraction,
retrieval, classification, and persistence.

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
- `POST http://127.0.0.1:8000/webhooks/mailgun/inbound`

The Mailgun webhook expects multipart form fields such as `sender`,
`recipient`, `subject`, `body-plain`, and one or more file fields like
`attachment-1`. If `MAILGUN_WEBHOOK_SECRET` is configured, requests must also
include Mailgun `timestamp`, `token`, and `signature` fields. Files are stored
under `data/uploads/{process_id}/`.

Attachment parsing and chunking use the Unstructured open source library.
Image/PDF OCR quality depends on the local Unstructured extras and system OCR
support available on the host.

## Tests

```powershell
python -m pytest
```

Runtime-only installs can use `requirements.txt`.

# CredRisk NTC score API

Single-file FastAPI service that scores NTC (new-to-credit) loan applications using weighted sections (income, tax, DTI, spending, hygiene, utility, investments, behavioural, enquiry). Weights and caps are driven by `scoring_weights.json` on disk; you can override them per request.

There is no database: you POST JSON bodies shaped like the bundled `test_cases.json`.

## Requirements

- Python 3.10+ recommended
- `python` / `python3` on your PATH

## Quick start

### Windows (PowerShell)

```powershell
.\run.ps1
```

Optional:

- `.\run.ps1 -Port 9000` — listen on another port
- `.\run.ps1 -NoInstall` — skip `pip install` (faster restarts if deps are already installed)

### macOS / Linux (bash)

```bash
chmod +x run.sh
./run.sh
```

Optional:

- `./run.sh --port 9000`
- `./run.sh --no-install`

### Manual

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt
uvicorn ntc_score_api:app --host 0.0.0.0 --port 8000
```

Then open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for interactive OpenAPI (Swagger UI).

## Project files

| File | Role |
|------|------|
| `ntc_score_api.py` | FastAPI app and scoring logic |
| `scoring_weights.json` | Default weights and configuration (edit on disk) |
| `test_cases.json` | Example payloads for `/score` |
| `requirements.txt` | `fastapi`, `uvicorn` |

## HTTP API (summary)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/scoring-config` | Current merged weights (from JSON + memory) |
| POST | `/scoring-config/reload` | Re-read `scoring_weights.json` without restart |
| POST | `/score` | Score one object or a batch (array). Optional top-level `scoring_config` merges over defaults for that call only |

## Example: score with curl

Replace `payload.json` with a snippet from `test_cases.json` or a full file:

```bash
curl -s -X POST http://127.0.0.1:8000/score \
  -H "Content-Type: application/json" \
  -d @test_cases.json
```

CORS is enabled for browser clients (`allow_origins=["*"]` in code).


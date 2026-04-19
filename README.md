# 🚀 NTC Loan Surrogate Scorecard API

A **production-ready FastAPI-based scoring engine** designed to evaluate **New-To-Credit (NTC)** loan applicants using a **rule-based surrogate scorecard**.

This system processes **nested JSON input (like real-world financial data)** and outputs:

* 📊 Credit score
* 📈 Section-wise breakdown
* ⚠️ Hard decline flags
* 🏷️ Risk band classification (Auto Approve / Review / Reject)

---

## 📌 Key Features

* 🔹 **End-to-end scoring engine** (Income → Behaviour → Enquiry)
* 🔹 **Configurable weights system** via `scoring_weights.json`
* 🔹 **Dynamic override support** per API request
* 🔹 **Handles both single & batch applications**
* 🔹 **Hard decline logic** (fraud, DTI breach, enquiry overload)
* 🔹 **Detailed section-level scoring breakdown**
* 🔹 **Swagger UI support for testing**

---

## 🏗️ Architecture Overview

```
Nested JSON Input
        ↓
Feature Engineering (nested → flat)
        ↓
Section-wise Scoring
        ↓
Hard Decline Checks
        ↓
Final Score Aggregation
        ↓
Risk Band Classification
```

---

## 📂 Project Structure

```
.
├── ntc_score_api.py        # Main FastAPI application
├── scoring_weights.json   # Configurable scoring rules
└── test_cases.json        # Sample input payloads
```

---

## ⚙️ Installation & Setup

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


#### ✅ Supports:

* Single JSON object
* Array of objects (batch processing)

---

## 📊 Sample Input

```json
{
  "income": {
    "salary_credit_regularity": 12,
    "income_growth_percentage": 8,
    "employer_category": "PRIVATE_LTD",
    "job_tenure_months": 24,
    "net_monthly_income": 48000
  },
  "dti": {
    "dti_ratio": 30
  },
  "spending": {
    "monthly_savings_rate": 10
  }
}
```

---

## 📤 Sample Output

```json
{
  "application_id": "example-app-id",
  "hard_decline": false,
  "total_score": 720.5,
  "max_score": 1000,
  "score_percentage": 72.05,
  "risk_band": {
    "band": "Standard NTC",
    "decision": "Auto Approve",
    "max_loan": 50000,
    "interest_rate": "20-24% p.a."
  }
}
```

---

## 🧠 Scoring Logic Breakdown

The model evaluates **9 major sections**:

1. 💼 Income & Employment
2. 🧾 Tax Identifiers
3. 📉 Debt-to-Income (DTI)
4. 💳 Spending Pattern
5. 🏦 Account Hygiene
6. 📱 Utility Payments
7. 📊 Investments
8. 🤖 Behavioural Signals
9. 🔍 Enquiry History

Each section contributes to the **final score (default max: 1000)**.

---

## 🚫 Hard Decline Rules

Application is instantly rejected if:

* ❌ Fraud / KYC flag detected
* ❌ Rooted / emulator device
* ❌ DTI exceeds threshold
* ❌ Too many recent enquiries
* ❌ Cooling period violation

---

## 🔧 Configurable Scoring System

All scoring logic is controlled via:

```
scoring_weights.json
```

### 🔹 Features:

* Section-wise max scores
* Threshold bands
* Risk band mapping
* Hard decline rules

### 🔹 Override Example (Per Request)

```json
{
  "scoring_config": {
    "sections": {
      "income": {
        "max": 200
      }
    }
  }
}
```

---

## 📈 Use Cases

* 🏦 NBFC / Fintech loan underwriting
* 📱 Digital lending apps
* 🧪 Risk model prototyping
* 📊 Credit decision simulations
* 🤖 AI + rule hybrid scoring systems

---

## 🔮 Future Enhancements

* ML-based calibration on top of rule engine
* Explainable AI (SHAP-based insights)
* Real-time bureau integration
* Fraud detection models
* Segment-based scoring (Freelancer / MSME / Salaried)

---




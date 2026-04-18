Here’s a clean, **premium-quality `README.md`** for your project based on your codebase 👇

---

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

### 1️⃣ Install Dependencies

```bash
pip install fastapi uvicorn
```

### 2️⃣ Run the API

```bash
uvicorn ntc_score_api:app --host 0.0.0.0 --port 8000
```

### 3️⃣ Open Swagger UI

```
http://localhost:8000/docs
```

---

## 📥 API Endpoints

### 🔹 Health Check

```
GET /health
```

---

### 🔹 Get Active Scoring Config

```
GET /scoring-config
```

---

### 🔹 Reload Weights (No Restart Needed)

```
POST /scoring-config/reload
```

---

### 🔹 Score Application(s)

```
POST /score
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

## 🧑‍💻 Author

Built as a **risk-engineering-first scoring system** focusing on:

* Interpretability
* Flexibility
* Production readiness



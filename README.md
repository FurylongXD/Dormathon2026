# Credibell
An AI-powered Loan Underwriting & Multi-Bank Eligibility Engine for Malaysian Consumers.

### Problem Statement
Applying for a loan can be complicated and frustration for a average joe. Customer would often need to rely on sales agents, bank agents or searching online on the loan application process, what documents that are needed, and what are the requirements for the loan approval. Even after submitting all the documents, the wait for the loan status often makes the applicants anxious, as they would need to plan for future arrangements, or if their loan application is rejected, they would need to quickly submit another application to another bank. Furthermore, any delays due to incomplete documents submitted or background of the applicants that may require further check may frustrate the applicant since the status is mostly undisclosed and requires further communications between the applicants and the banks, which is susceptible to miscommunication, or arguments happening. 

Existing digital application channels may simplify online submissions, but applicants can still struggle to understand their requirements and prepare complete applications before submitting them for review.

Credibell aims to address these challenges by providing an AI-powered, one-stop loan application assistant that automates document ingestion, extracts structured financial features, runs an explainable SHAP-backed credit risk model, and matches applicant profiles against real-time Malaysian bank lending criteria.

### Features:
1. Localized Document Ingestion
- Automated parsing and structured feature extraction from Malaysian financial documents:
  a. CCRIS & CTOS: Credit history, outstanding balances, DSR (Debt Service Ratio), and payment track record.
  b. EPF / KWSP & Payslips: Income verification, contribution consistency, and net monthly cash flow.

2. Hybrid Credit Scoring & Explainability Engine
- Deterministic Scoring: Quantitative ML scoring models that eliminate LLM math hallucinations.
- Explainable AI: Computes SHAP (SHapley Additive exPlanations) values for every decision, providing applicants and underwriters with exact feature attributions for approval or rejection.

3. RAG-Driven Multi-Bank Policy Matching
- Integrates RAG retrieval against structured bank policy rulebooks.
- Cross-references user financial profiles across local bank catalogs to suggest optimal loan products, tenures, and interest rates.
- Interactive "What-If" Loan Scenario Simulator

4. Production Engineering & Diagnostics
- Built-in diagnostic utilities for pipeline integrity, metric tracking, and comprehensive validation benchmarks.

### System Architecture

                                    +-----------------------+
                                    | Raw Document Uploads  |
                                    | (CCRIS, CTOS, EPF)    |
                                    +-----------+-----------+
                                                |
                                                v
                                    +-----------------------+
                                    | Document Parser       |
                                    | (documents.py)        |
                                    +-----------+-----------+
                                                |
                                                v
                                    +-----------------------+
                                    | Structured Feature    |
                                    | Extraction (schema.py)|
                                    +-----------+-----------+
                                                |
                    +---------------------------+---------------------------+
                    |                                                       |
                    v                                                       v
     +------------------------------+                       +------------------------------+
     |   Quantitative ML Engine     |                       |      RAG Retrieval Engine    |
     | (predictors.py / finance.py) |                       |   (retrieval.py / LLM)       |
     +--------------+---------------+                       +--------------+---------------+
                    |                                                       |
                    v                                                       v
     +------------------------------+                       +------------------------------+
     |  SHAP Explainability Engine  |                       |  Bank Policy Catalog Match   |
     |      (shap_engine.py)        |                       | (bank_catalog.json/policies) |
     +--------------+---------------+                       +--------------+---------------+
                    |                                                       |
                    +---------------------------+---------------------------+
                                                |
                                                v
                                    +-----------------------+
                                    | Comprehensive Credit  |
                                    | & Eligibility Report  |
                                    +-----------------------+

### Tech Stack
- Frontend: Streamlit
- Backend: Python FastAPI

### Prerequisite
- Python 3.10 or higher
- Virtual environment tool (env)

### How to Run
Extract **credibell_loan_app.zip**. Double-click **start.cmd** in the extracted folder.

For a faster upgrade of an already working project, copy the files inside the ZIP's `credibell_loan_app` folder into your current project folder. Keep your existing `.venv` and private `.env`; the ZIP contains neither, so they do not need to be replaced. Stop the old server before copying, then double-click `start.cmd`. No dependency versions changed in this update.

The launcher creates `.venv` if needed, checks installed package versions without importing the ML libraries, installs only when requirements are missing or changed, then starts CrediBell and opens the browser when the server is ready. First setup needs Python 3.12/3.13 and internet for dependencies; later starts skip pip when everything is installed. Keep the terminal running; Ctrl+C stops the app.

In VS Code, open the folder containing `launch.py`, then run:

```powershell
python launch.py
```

If `python` is unavailable, use `py -3 launch.py`. You do not have to create or activate `.venv` manually. Existing manual `run.py` commands still work. For setup only use `python launch.py --setup`; for a read-only installation check use `python launch.py --check`. For another port use `python launch.py --port 8503`. `--no-browser` suppresses automatic browser opening. Preserve your existing private `.env` when upgrading.

Open **http://127.0.0.1:8502/** if the browser does not open. Python 3.12.14 was used for validation; 3.13 is the intended source-compatible target. First download/OCR/model load times depend on the computer and connection; dependencies cannot be skipped on a fresh machine.

### Required content in other mock layouts

Every image/PDF needs a visible **SAMPLE/MOCK/SYNTHETIC** marker and issue date. An anonymous ID is recommended; when absent, the local session groups the document. All documents must reconcile to one applicant. `server/ocr_adapter.py` defines the label aliases; `loan_engine/documents.py` defines the complete schema.

| Slot | Required financial information |
|---|---|
| Profile | Age; citizenship/nationality |
| Payslip | Three consecutive `month_1..3` dates; gross, net, employee EPF, tax/PCB and other deductions for each month |
| Bank statement | Matching three month dates; income credits and living expenses per month; available cash savings |
| EPF | Matching month dates; employee contribution per month; total balance; regular contribution months |
| CCRIS | Anonymous card/loan account aliases; monthly card/loan payments; card balance/limit; loan balance; maximum arrears months; late payments in 12 months; outstanding housing-loan count |
| CTOS | Mock reported score; legal-record flag |
| Credit card | Account alias; balance; limit; minimum due; annual interest rate |
| Existing loan | Account alias; balance; monthly payment; early-settlement fee |
| Employment | Months in current job; contract months remaining; variable-income fraction |
| Loan quotation | Product; purchase price; loan amount; deposit; vehicle age for car; one or two bank offers, each with bank code/name, annual rate, explicit rate method, months, upfront fees and variable-rate flag |

Use explicit units: `Interest rate 1: 5.3%`, `Rate basis 1: reducing_nominal`, `Term months 1: 84`. `flat`, `reducing_nominal` and annually compounded `reducing_effective` have different formulas. An advertised "effective rate" does not automatically supply the last formula. Readable aliases cannot compensate for absent financial information. No manual financial override endpoint is exposed by the dashboard.

CCRIS commitments are reconciled with the card and loan statements so the same debt is not counted twice. Three salary months, net-to-bank credits, payroll deductions, EPF amounts, applicant/account aliases and quotation price/deposit/principal are matched. Documents and quotations are checked for recency.

### What each model predicts

| Component | Output and meaning |
|---|---|
| Approval XGBoost classifier | Calibrated generic probability of a **synthetic** underwriting approval for the quoted amount, rate and term |
| Credit-risk XGBoost classifier | Separate probability of at least one 90+ day arrears event over the next 12 months; not `1 − approval` |
| Credit-health XGBoost regressor | Expected synthetic internal health score from 0–100; **not** a forecast official CTOS score |
| `RiskRatingModel` | Custom A–F bands from the arrears model: A <3%, B <8%, C <15%, D <30%, E <50%, F ≥50% |
| `ShapEngine` | Exact XGBoost TreeSHAP for all three models; approval/risk effects add in calibrated log-odds, health effects in internal score points |
| Policy + finance | Partial published eligibility checks, instalments, DSR, LTV, disposable income, deposit, fees, total cost and illustrative financing ceiling |
| Counterfactual engine | Changes debts/deposit/amount/term/employment scenario and reruns the same models/policies; ranks feasible improvements with costs and cash reserve |

SHAP is an explanation component, not another predictor. A–F follows risk thresholds; its explanation comes from risk SHAP. SHAP is not causal advice. Recommendations are locally generated from calculated scenarios, with assumptions, emergency reserves and new-document/quote requirements. Repaying a balance does not erase historical arrears. No LLM invents approval gains or score changes.

Training uses **16,000 fully synthetic records**, with separate training, early-stopping, calibration and untouched test subsets. The included previous 1,000-row dataset was not assumed to contain bank-specific approval/arrears outcomes. No real bank outcomes are available here. `artifacts/metrics.json` reports synthetic holdout performance; it does not establish real-world accuracy. Out-of-training-range input suppresses probability and SHAP output. Private bank acceptance rules, real bureau access and real loan approval are unavailable.

The financing estimate combines supported published product ceilings with a disclosed **60% net-income DSR planning assumption**, living costs and cash availability. That 60% is not claimed as a universal Malaysian bank rule. The illustration of 90% financing / 10% deposit applies only where the relevant product/vehicle-age conditions support it. Upfront fees and affordability may change cash needs.

Published bank terms were reviewed on **10 October 2026**; the base snapshot expires **9 November 2026**. Quotes must be recent. Online extraction does not silently extend inherited BNM/base-policy safeguards. A maintainer must recheck official sources and update the dated configuration before expired policies can be used. Sample document dates also age: `python refresh_samples.py` regenerates synthetic images for today; it does not reverify policy dates.

### Team Members (LunchBuddies)
1. Lucius Long Kai Xuan
2. Tey Kaize
3. Darren Yap Zhen Jie
4. Shamin Hossain







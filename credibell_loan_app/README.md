# CrediBell: document-to-loan models and dashboard

A complete local VS Code project with a Python API, trained XGBoost models, image/PDF OCR with evidence-checked Grafilab field translation, exact TreeSHAP, public bank retrieval through Grafilab, and three banking-style dashboard pages. No Node build or Streamlit is required. The frontend is HTML/CSS/JavaScript; all financial results come from the Python engine.

## 1. Fast Windows setup

Extract **credibell_loan_app.zip**. Double-click **start.cmd** in the extracted folder.

For a faster upgrade of an already working project, copy the files inside the ZIP's `credibell_loan_app` folder into your current project folder. Keep your existing `.venv` and private `.env`; the ZIP contains neither, so they do not need to be replaced. Stop the old server before copying, then double-click `start.cmd`. No dependency versions changed in this update.

The launcher creates `.venv` if needed, checks installed package versions without importing the ML libraries, installs only when requirements are missing or changed, then starts CrediBell and opens the browser when the server is ready. First setup needs Python 3.12/3.13 and internet for dependencies; later starts skip pip when everything is installed. Keep the terminal running; Ctrl+C stops the app.

In VS Code, open the folder containing `launch.py`, then run:

```powershell
python launch.py
```

If `python` is unavailable, use `py -3 launch.py`. You do not have to create or activate `.venv` manually. Existing manual `run.py` commands still work. For setup only use `python launch.py --setup`; for a read-only installation check use `python launch.py --check`. For another port use `python launch.py --port 8503`. `--no-browser` suppresses automatic browser opening. Preserve your existing private `.env` when upgrading.

Open **http://127.0.0.1:8502/** if the browser does not open. Python 3.12.14 was used for validation; 3.13 is the intended source-compatible target. First download/OCR/model load times depend on the computer and connection; dependencies cannot be skipped on a fresh machine.

## 2. Try the complete document flow

On **Submit documents**, choose a car, home or personal sample and select **Use sample documents**. This reads the ten PNGs through real local OCR, verifies them and saves the uploads. Select **Submit & analyse** to run the models. Sample loading replaces this session's previous uploads and analysis.

To upload your own anonymized sample images or PDFs:

1. Confirm the mock-document checkbox.
2. For each slot select **Upload document**. Reading starts automatically after selection once the sample checkbox is confirmed; otherwise confirm it and select **Verify**.
3. Inspect **View** to check the extracted fields and preview.
4. Select **Save upload** for each verified document.
5. Once all ten are saved, select **Submit & analyse**. Cross-document checks can still stop submission.

The ten slots are **profile, payslip, bank statement, EPF, CCRIS, CTOS, credit card, existing loan, employment contract and loan quotation**. Profile supplies age plus the financial documents; age alone does not determine the outcome. No identity-document number is needed. Use anonymous applicant/account aliases across related mock documents. Zero balances/payments must be explicitly stated; the app does not infer missing debts as zero. This first schema requires a positive card limit and a mock reported score. Profiles without a card or bureau score need a schema/training update and are stopped rather than given invented values.

**PNG/JPEG/WEBP or PDF**, up to 12 MB per upload. Images are limited to 12 megapixels; PDFs support 1–8 pages in one slot. Put three salary months in one payslip PDF, for example. Scanned and text PDFs are rendered and read from their visible page images, so a hidden text layer is not the financial source. Password-protected, oversized, illegible or incomplete files are rejected.

**AI reading of unfamiliar layouts:** local OCR first recognizes the page text. If the labelled reader cannot fill the required schema and Grafilab is configured, the AI maps the visible text to fields, with exact page/line references for every value. Python checks source occurrences, units, required values, dates, confidence and supported calculations; submission then reconciles the documents. A clear image helps, but no system can guarantee accurate reading of every layout. Always use **View** and compare the extracted fields with the source before saving. Read-confidence percentages measure legibility, not verified accuracy or authenticity.

Supported AI recipes include direct values, explicitly labelled salary/living-cost sums, commission/gross-income ratios, age from birth/issue dates, and employment durations from dates. Unlabelled transfers are not classified as salary; unknown fees/debts are not assumed zero. A missing field or unsupported rate basis stops the read. There is no manual financial override.

Try the four PDFs in **sample_documents/pdf/**. **profile.pdf** and the three-page **bank_statement.pdf** work offline with the car set. **profile_birth_date.pdf** and **payslip_table.pdf** demonstrate layouts requiring AI interpretation. Their OCR-to-recipe validation is tested with controlled provider responses; actual Grafilab inference requires your account. The alternate English/Malay PNGs remain supported.

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

## 3. Configure your EXISTING Grafilab key

Local predictions and recommendations work without an LLM. Grafilab now has **two separate functions**: translating visible anonymized sample-document text into model fields, and extracting public policy/rate references from freshly fetched official pages. Images and PDFs are not sent to the provider, but recognized sample text is sent for AI reading of unfamiliar layouts. The upload checkbox explains this. Public bank requests never contain the applicant profile. Do not use genuine personal documents.

From the project terminal:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Open `.env` in VS Code, put your existing key after `GRAFILAB_API_KEY=`, and keep:

```dotenv
GRAFILAB_BASE_URL=https://llm.grafilab.ai/v1
GRAFILAB_MODEL=
```

List account-accessible models:

```powershell
.\.venv\Scripts\python.exe -m loan_llm models
```

Set `GRAFILAB_MODEL` to an available **chat** model ID returned by your account. No model download or guessed DeepSeek model is required. Environment variables override `.env`; remove an old PowerShell `GRAFILAB_MODEL` value if it is overriding your file. Restart the server after changing settings.

When configured, submission refreshes official sources for the quotation's banks, caches successful public contexts for one hour, and overlays supported verified fields into the policy engine. **Refresh bank terms** checks all comparison banks for the current loan type and reruns the analysis. Failed online checks retain their explicitly dated snapshot status. Calls can consume Grafilab credits.

To inspect structured public information without an applicant:

```powershell
.\.venv\Scripts\python.exe -m loan_llm refresh-bank --bank-code PUBLIC_BANK_CAR --out results\public_bank_car.json
```

If the provider returns 403, run:

```powershell
.\.venv\Scripts\python.exe grafilab_diagnose.py
```

The diagnostic shows a safe status/code and request ID, not the key or error body. Resolve the reported account permission/billing-country issue with Grafilab. Regenerating a key is not the default remedy. Successful authenticated Grafilab inference could not be tested without your account credentials; the protocol and validation were tested with controlled responses.

### Online facts feeding the model

`loan_llm/retrieval.py` fetches bounded HTTPS HTML from an exact official-source allowlist. `loan_llm/live_policies.py` sends the fresh public text to Grafilab, validates the structured response against exact excerpts/numbers/units/ranges, and returns source URLs, timestamps, unknown fields, conditions and rate bases. `write_engine_policy_config()` overlays supported public policy fields; inherited offline safeguards are disclosed. LLM interpretation can still be wrong even when a quote exists: this is not verification of every product condition or a substitute for a bank-confirmed offer.

Unknown private DSR/credit-score cutoffs remain unknown. Failed retrieval or invalid extraction is labelled unavailable; old rates are not relabelled as live. Combined asset-and-fee margins are not treated as asset-only financing. The engine uses **the uploaded quotation** for actual payment/cost predictions and ranks only those quoted offers. Online rates remain indicative references. `public_rate_planning_quote()` is provided for a separately labelled synthetic what-if, requiring an explicit supported calculation basis and confirmed conditions; it never silently replaces an offer.

## 4. What each model predicts

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

## 5. Dashboard structure

The navy/blue/white visual design follows a banking layout with original CrediBell branding. It is not affiliated with Chase or a Malaysian bank.

- **Submit documents:** ten separate image/PDF uploads, local or AI extraction, source-linked field review and Save upload controls; final submission after all ten saves.
- **Prediction analysis:** monthly allocation and risk on the left; red-to-green approval outlook above SHAP in the centre; bank financing limits and amounts on the right; uploaded quotation comparison below. Car/home comparisons include Public Bank, Maybank, CIMB, RHB, Hong Leong and AmBank; personal comparisons include five banks.
- **Explanation & recommendation:** plain-language reasons, budget/credit-limit/cash-reserve infographics, before/after approval bars, scenario cash and repayment costs, risk/credit-health changes and future habits. Source and scenario assumptions are available in compact expandable details.

The top-right profile menu contains an anonymous session and **Clear my uploads and analysis**. The old empty top strip has been removed. No identity account or name field is required. Analysis is never prepopulated with fake chart values. Replacing/removing a saved upload invalidates the previous assessment; saved uploads survive refresh and server restart in the same browser session.

## 6. Files and integration into your repository

```text
run.py / setup.ps1 / start.cmd   Local launch and setup
server/app.py                   Same-origin API and job orchestration
server/ocr_adapter.py           Image/PDF rendering + OCR + label adapter
server/document_ai.py           Grafilab field recipes + source evidence checks
server/bank_comparison.py       Public limits separated from uploaded quotes
server/store.py                 SQLite session/upload/result persistence
web/                           Three dashboard pages, CSS and JavaScript
loan_engine/                   Feature engineering, finance, models, SHAP, scenarios
loan_llm/                      Grafilab client + allowlisted live policy/rate retrieval
artifacts/                     Three portable trained model JSON files + metadata/metrics
config/                        Dated bank policies/catalog + registered mock samples
sample_documents/              Car/home/personal/alternate images + four PDF samples
tests/                         Finance, matching, models, OCR parsing, provider and storage checks
runtime/                       Generated local data; excluded from Git and ZIP
```

Copy this folder into your repo as a service, preserving `artifacts/`, `config/`, `loan_engine/`, `loan_llm/`, `server/` and `web/`. Run it through `run.py`. Keep `.env`, `.venv` and runtime data out of Git. For an existing frontend, implement the same HTTP workflow below and route through your same-origin backend. Do not copy the key into browser code or trust client-supplied scores.

### Preparing for GitHub

- Commit source code, tests, documentation, launch/setup scripts, `requirements.txt`, `.gitignore`, and `.env.example`. The example must contain blank or placeholder credentials.
- Commit `artifacts/` as a complete model bundle: the three model JSON files and `metadata.json` are required for assessments; `metrics.json` records evaluation results.
- Commit `config/` and `loan_llm/bank_knowledge.json`. The app reads these files for mock registration, policies, comparisons, and its knowledge base. Do not add a blanket `*.json` ignore rule.
- Keep the synthetic `sample_documents/` files, their `manifest.json` files, and `expected_fields.json` files together. Only include verified mock documents; manifests support CLI/tests and expected fields support OCR verification. After refreshing samples, commit the matching `config/mock_registry.json` in the same change.
- Keep private `.env` variants, virtual environments, runtime uploads/database files, caches, training exports, results, and logs local. `.gitignore` excludes these and preserves `runtime/.gitkeep`.
- Python 3.12 was validated; 3.13 is the intended source-compatible target. A fresh checkout needs Python and internet for dependency installation. Run `python launch.py --setup`, then `python launch.py --check`. Copy `.env.example` to `.env` locally if using Grafilab. CPU execution is configured; no GPU or Node build is required. Minimum RAM/disk requirements have not been measured.
- Review `git status --short`, `git diff --cached --stat`, and `git diff --cached` before committing. Ignore rules do not remove files already tracked or erase earlier commits. Rotate exposed credentials and address repository history if needed.

The base policy snapshot expires on 9 November 2026. Reverify the sources before updating policy dates; refreshing sample documents does not renew the policy snapshot.

| API | Use |
|---|---|
| `GET /api/bootstrap` | Starts/reuses anonymous HttpOnly session; returns CSRF token and saved state |
| `POST /api/documents/{kind}/verify` | Raw image/PDF body; headers `X-CSRF-Token`, `X-Mock-Only: true`; returns verified digest |
| `POST /api/documents/{kind}/save` | JSON `{ "digest": "..." }`; confirms the currently verified version |
| `GET /api/documents/{kind}` | Read extracted fields to review |
| `GET /api/documents/{kind}/preview` | Sanitized first-page PNG preview (all PDF pages are read) |
| `POST /api/assess` | Run the saved complete set; returns job ID |
| `GET /api/jobs/{id}` | Poll progress/completion/error for this session |
| `GET /api/result` | Latest valid assessment |
| `POST /api/refresh-banks` | Force public bank refresh and re-assessment |
| `GET /api/result/download` | Download calculation/explanation JSON |
| `POST /api/clear` | Logically delete this session's uploads, jobs and result |

Mutations require the CSRF header and session cookie. The browser automatically retains the cookie. Do not loosen origin/session checks to avoid configuring a proper same-origin integration.

Optional model-only commands:

```powershell
.\.venv\Scripts\python.exe -m loan_engine assess --docs sample_documents\car --out results\car.json
.\.venv\Scripts\python.exe -m loan_engine train --rows 16000 --out artifacts --export-data data\synthetic_training.csv
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe verify_images.py
.\.venv\Scripts\python.exe verify_ai_documents.py
```

With the server already running, `python verify_api.py` verifies the full HTTP flow in isolated synthetic sessions. It also checks CSRF/origin protection, separate save actions, alternate layouts, PDFs, six-bank comparison and assessment invalidation.

Training overwrites your local model artifacts; pretrained models are already included. The model CLI accepts registered generated fixtures; the web/API reader also accepts mapped alternate mock layouts. `verify_images.py` reads all supplied images through actual OCR.

## 7. Privacy, policy and deployment limits

This delivery implements a **synthetic-only local prototype**, not a legally certified consumer credit service. A visible mock watermark, self-attestation and limited identifier checks do not prove anonymization: never upload genuine ICs, names, bank-account numbers or real financial records. Extracted values, source evidence and a sanitized first-page preview are saved to a local SQLite file for the Save upload feature. Original PDF files are discarded after reading; page/line source text is retained for review. Saved data is not encrypted at rest. AI reading sends only anonymized sample OCR text to Grafilab, so local storage does not mean all processing is local. Sessions expire after 24 hours and are cleaned on a later bootstrap; Clear performs logical deletion, not secure erasure of backups or SQLite pages.

The server binds to `127.0.0.1`, has same-origin/CSRF checks, HttpOnly session cookies, bounded file bodies, a restrictive content policy and no access logs. This is not multi-user production authentication. There is no automatic submission to banks, CCRIS/CTOS connection, identity verification or claim that a bureau score is changed. A real deployment needs lawful collection/access, security review, consent/notice/retention controls, bureau licensing, human review, real outcome validation and applicable Malaysian legal assessment, including any cross-border provider processing. These are outside this mock-only build.

Bank Negara's guidance states that rejected applications are not included as rejected applications in CCRIS; BNM does not issue a credit rating or blacklist borrowers. This app avoids the earlier “rejection footprint automatically ruins credit” premise. Check the [official CCRIS FAQ](https://www.bnm.gov.my/faqs/ccris/questions), the [Malaysian PDPA/Amendment resources](https://www.pdp.gov.my/ppdpv1/en/akta/pdp-act-2010-en/), and the linked product sources in `config/bank_policies.json` before designing a real service. Internal lender decisions remain outside this prototype's knowledge.

See **VALIDATION.md** for what was actually tested and the unresolved external-service limits.

## CrediBell performance update

OCR assets warm in the background while the dashboard opens. Upload selection automatically begins reading, with separate transfer/read status. PDF rendering and image conversion are shared by reading and preview generation, rather than repeated. Re-uploading identical bytes into the same slot and local session reuses the verified extraction and returns it for review; changed bytes are read afresh, and replacement invalidates the previous analysis. Extraction results are never shared across sessions. No resolution, confidence threshold or reconciliation checks have been reduced.

The duplicate bottom bank table was removed. The right-hand comparison now contains uploaded quoted rates and calculation methods, effective rates including fees, quoted terms, repayments, loan amounts, upfront fees and total financing costs. Unquoted products show published limits/terms and request a quotation for borrower-specific rates or repayments. Existing saved analyses can supply quote details; resubmit for a newly generated comparison after upgrading.

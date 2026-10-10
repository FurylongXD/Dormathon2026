# CrediBell performance and bank-panel update - 10 October 2026

- 94 unit tests passed on Python 3.12.14, including session/slot cache isolation, changed-byte rereading, shared render/preview, and installer version checks. The suite also passed with pinned PDFium 5.13.0.
- Actual PDF OCR plus controlled evidence-checked AI mapping passed with PDFium 5.13.0. No authenticated Grafilab call was made.
- Existing isolated HTTP integration passed: ten uploads, image/PDF OCR, CSRF/origin, separate saves, predictions, quotes, six bank products, SHAP reconstruction and result invalidation.
- Browser verified automatic PDF reading without clicking Verify, separate saving and submission, CrediBell title/logo, six-bank details, quoted rates/methods/terms/fees/repayments and removal of the bottom bank table. Desktop/mobile widths had no horizontal overflow; no browser warnings or errors appeared.
- Automatic setup's already-installed path ran successfully without pip installation. Version checks include inherited dependency paths in this test runtime. Fresh internet dependency installation and automatic launching of the user's default external browser were not repeated here; launcher creation/check/install paths use standard Python subprocesses.
- Measured local warm-server timings: fresh profile PNG 1.073 s; same bytes/slot/session 0.027 s. Fresh three-page statement PDF 5.838 s; identical repeat 0.032 s. These measure extraction reuse, not general first-upload accuracy or a guaranteed speed on other computers. Confidence, original-byte digest and field counts match for fresh/reused results. PDF rendering is now called once for OCR and preview instead of twice.
- Financial models, evidence thresholds and reconciliation checks are unchanged. Quoted borrower rates remain separate from public bank limits and conditional online references.

Earlier model validation and deployment limits follow.

# Version 2 validation — 10 October 2026

## Executed checks

- **90 unit tests passed** on Python 3.12.14/Windows. Finance, policy expiry, loan limits, matching/debt deduplication, separate outcomes, coverage checks, SHAP reconstruction, scenarios, storage, provider errors and public-bank extraction still pass. New tests cover source evidence, invented/sub-string values, missing income, low-confidence sources, date-derived age, duplicate/unlabelled transactions, sample/privacy checks, PDF rendering and six-bank limits. Combined home margins including insurance/fees are not used as asset-only percentages.
- **Actual PDF/OCR checks passed:** profile.pdf (1 page) and bank_statement.pdf (3 pages) return the expected fields offline. profile_birth_date.pdf (1 page) and payslip_table.pdf (3 pages) pass rendering/OCR followed by controlled source-linked AI recipes. These test the adapter, not paid Grafilab extraction. PDF samples were rendered and visually checked.
- **Updated HTTP integration passed** against localhost with actual image/PDF OCR: isolated cookies/jobs, CSRF/origin, separate verify/save, wrong digest, ten required documents, PDF replacement, evidence/page counts, alternate quotation, six bank references, two quoted offers, three SHAP reconstructions, persistence, invalidation and clearing the test session.
- **Browser flow verified:** profile PDF selected in the file picker, read, reviewed, saved and submitted with nine other records. Six-bank comparison, quote switching, three SHAP views, explanations and action charts inspected. Desktop/mobile layout screenshots are in the parent outputs folder. No warnings/errors appeared in the checked browser flow.
- JavaScript syntax and Python compilation checked. The original 32 supplied PNGs were read against independent fixture values in version 1; version 2 integration again exercises the ten-document car set and alternate profile/quotation with actual OCR.

## Limits of the evidence

Models retain 16,000 synthetic training records and reserved calibration/test sets. Holdout AUC is about 0.887 for approval and 0.878 for 90+ day arrears; internal-health MAE about 6.4 points. These do not establish real bank approval accuracy. There is no bank-specific outcome dataset, real CCRIS/CTOS access or official credit-score prediction. Example car results are around 67.8% model approval estimate, 19.4% synthetic serious-arrears risk, grade D and 66/100 internal health.

**No authenticated Grafilab inference was executed:** a working user key/account model was unavailable. Client/evidence tests use controlled responses. A previous 403 remains an account/provider matter; grafilab_diagnose.py gives safe diagnostics. Unfamiliar layouts require an accessible chat model. Anonymized sample OCR text can now leave this computer for Grafilab; uploaded file bytes do not. Watermarks and identifier checks are not comprehensive anonymization.

AI mapping can misinterpret a table despite source-occurrence checks. Missing data, unclassified transfers, unknown fees, unsupported rate bases and inconsistent records are stopped. Review every extraction. Universal layout or handwriting accuracy is not claimed. The current model schema requires a positive card limit and a mock bureau score.

Official product references cover six car/home and five personal banks. Published maximums and indicative online rates are separate from quotations, not approved amounts. Some asset-only home margins are unknown or planning assumptions. Policy/catalog review: 10 October 2026; expiry: 9 November 2026. Live refresh does not extend inherited safeguards. Source interpretation still requires care.

Python >=3.12 is the source target; testing used 3.12.14, not the user's 3.13 installation. Original PDFs are discarded after reading; first-page previews and evidence remain locally. Saved data is not encrypted at rest. Production authentication, real-data validation and legal certification are outside this sample implementation.

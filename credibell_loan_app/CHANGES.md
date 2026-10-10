# CrediBell update

- Renamed the application and download to CrediBell.
- One-click start.cmd automatically creates/checks the environment and installs dependencies only when needed.
- OCR warms in the background; uploads automatically read after selection, with progress status.
- Reuse the rendered pages for preview. Identical uploads reuse verified extraction only in the same session/slot; changed files are read anew.
- Removed the bottom bank table. Expanded the right-hand panel with quoted rate/method, effective rate, term, repayment, fees and financing cost.
- Keep your private .env when upgrading. Extract to a fresh folder; run start.cmd, reload, and resubmit if needed.

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from schema import AssessmentError
from documents import DocumentKind, DocumentSubmission, LocalOCR
from engine import LoanAssessmentEngine

def main():
    parser = argparse.ArgumentParser(
        description="Synthetic document-to-loan model CLI. Dashboard: python run.py"
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # Train subcommand
    train = subs.add_parser("train")
    train.add_argument("--out", default="artifacts")
    train.add_argument("--rows", type=int, default=16000)
    train.add_argument("--seed", type=int, default=20261010)
    train.add_argument("--export-data", default="data/synthetic_training.csv")

    # Make-demo subcommand
    demo = subs.add_parser("make-demo")
    demo.add_argument("--out", default="sample_documents/car")
    demo.add_argument("--product", choices=["car", "home", "personal"], default="car")
    demo.add_argument("--as-of", default="2026-10-10")
    demo.add_argument("--demo-id", default="DEMO00001")

    # Assess subcommand
    assess = subs.add_parser("assess")
    assess.add_argument("--docs", default="sample_documents/car")
    assess.add_argument("--models", default="artifacts")
    assess.add_argument("--out", default="results/assessment.json")
    assess.add_argument("--as-of", default="2026-10-10")

    args = parser.parse_args()

    try:
        if args.command == "train":
            from .training import train_models

            metrics = train_models(args.out, args.rows, args.seed, args.export_data)
            compact = {
                k: {
                    metric: value
                    for metric, value in v.items()
                    if metric != "calibration_bins"
                }
                for k, v in metrics["models"].items()
            }
            print(json.dumps(compact, indent=2))

        elif args.command == "make-demo":
            from .demo_documents import make_demo

            result = make_demo(
                args.out, args.product, demo_id=args.demo_id, as_of=args.as_of
            )
            print(
                f"Created {len(result['files'])} anonymous mock images in {Path(args.out).resolve()}"
            )

        elif args.command == "assess":
            from .documents import DocumentKind, DocumentSubmission, LocalOCR
            from .engine import LoanAssessmentEngine

            docs = Path(args.docs)

            # Pre-instantiate LocalOCR ONNX engine once to share across worker threads
            shared_ocr = LocalOCR()
            submission = DocumentSubmission(docs / "manifest.json", ocr=shared_ocr)

            slots = [kind for kind in DocumentKind]

            # Worker function: Reads bytes AND executes OCR inside thread workers
            def process_and_verify_slot(kind):
                path = docs / f"{kind.value}.png"
                content = path.read_bytes()
                submission.add_document(kind, path.name, content)
                return kind.value

            print(
                "Running parallel local ONNX OCR across 10 document slots...",
                flush=True,
            )

            # Run OCR inference concurrently across CPU worker threads
            with ThreadPoolExecutor(max_workers=min(10, len(slots))) as executor:
                results = executor.map(process_and_verify_slot, slots)
                for verified_kind in results:
                    print(f"OCR verified: {verified_kind}", flush=True)

            # Compile cross-document audit & evaluate scoring engine
            applicant, quotes, audit = submission.compile(args.as_of)
            result = LoanAssessmentEngine(args.models).assess(
                applicant, quotes, args.as_of, audit
            )

            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
            )
            print(f"Saved assessment: {out.resolve()}")

    except (AssessmentError, FileNotFoundError, ValueError) as error:
        parser.exit(2, f"Assessment stopped: {error}\n")


if __name__ == "__main__":
    main()
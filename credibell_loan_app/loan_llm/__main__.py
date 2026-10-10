"""python -m loan_llm models | refresh-bank --bank-code ..."""
import argparse
import json
from pathlib import Path
from .client import ServiceError
from .service import LoanLLMService
from .live_policies import BANK_PRODUCTS

def main():
    parser=argparse.ArgumentParser(description='Grafilab public bank policy and rate extraction')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('models',help='List models accessible to your existing API key')
    refresh=commands.add_parser('refresh-bank',help='Fetch official sources now, extract and validate their public terms')
    refresh.add_argument('--bank-code',required=True,choices=list(BANK_PRODUCTS))
    refresh.add_argument('--out',type=Path)
    args=parser.parse_args()
    try:
        service=LoanLLMService()
        result=service.client.models() if args.command=='models' else service.live_bank_context(args.bank_code)
        output=json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)
        if getattr(args,'out',None):
            args.out.parent.mkdir(parents=True,exist_ok=True)
            args.out.write_text(output+'\n',encoding='utf-8'); print(f'Saved {args.out.resolve()}')
        else: print(output)
        return 0
    except ServiceError as error:
        print(json.dumps({'error':error.public()})); return 1

if __name__=='__main__': raise SystemExit(main())

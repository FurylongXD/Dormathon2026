"""Regenerate anonymous documents for a date. Does NOT reverify bank policies."""
import argparse
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from PIL import Image,ImageDraw
from loan_engine.demo_documents import make_demo,fixture_fields,font

ROOT=Path(__file__).resolve().parent

def alternate_documents(as_of):
    out=ROOT/'sample_documents/alternate'; out.mkdir(parents=True,exist_ok=True)
    fields=fixture_fields('car',as_of=as_of)
    date_label=datetime.fromisoformat(as_of).strftime('%d/%m/%Y')
    rows={'profile':['Statement date: '+date_label,'Anonymous id: DEMO00001','Umur: 32','Nationality: Malaysian'],
          'loan_quotation':['Issue date: '+date_label,'Anonymous id: DEMO00001','Loan type: Car',
              'Vehicle price: RM100,000','Loan amount: RM90,000','Cash deposit: RM10,000','Car age: 0',
              'Bank name 1: Public Bank','Interest rate 1: 5.3%','Rate basis 1: reducing_nominal',
              'Term months 1: 84','Upfront fees 1: RM100','Variable rate flag 1: 0',
              'Bank name 2: Maybank','Interest rate 2: 5.8%','Rate basis 2: reducing_effective',
              'Term months 2: 84','Upfront fees 2: RM200','Variable rate flag 2: 0']}
    for kind,lines in rows.items():
        im=Image.new('RGB',(1500,230+64*len(lines)),'#ffffff'); draw=ImageDraw.Draw(im)
        draw.rectangle((0,0,1500,100),fill='#133859')
        draw.text((45,24),'SYNTHETIC MOCK / ANONYMOUS SAMPLE',fill='white',font=font(36))
        # Large dark watermark remains readable when the tall quotation is resized by OCR.
        draw.text((45,124),'SYNTHETIC SAMPLE ONLY',fill='black',font=font(36))
        for i,line in enumerate(lines): draw.text((45,194+64*i),line,fill='black',font=font(34))
        im.save(out/(kind+'.png'),optimize=True)
    (out/'README.txt').write_text('Unregistered alternate mock layouts. Use these two images with the other eight car sample images. They contain the same synthetic financial values, with different English/Malay labels and explicit RM/% units.\n',encoding='utf-8')

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--as-of',default=datetime.now(timezone(timedelta(hours=8))).date().isoformat()); args=parser.parse_args()
    combined={'synthetic_only':True,'files':{}}
    for product in ('car','home','personal'):
        registry=make_demo(ROOT/'sample_documents'/product,product,as_of=args.as_of)
        combined['files'].update(registry['files'])
    (ROOT/'config/mock_registry.json').write_text(json.dumps(combined,indent=2),encoding='utf-8')
    alternate_documents(args.as_of)
    print('Generated 30 registered + 2 alternate mock images. Bank policy dates were not changed.')

if __name__=='__main__': main()

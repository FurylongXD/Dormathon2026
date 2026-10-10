"""Separate public product ceilings from calculated uploaded quotations."""
from datetime import date
import json
from pathlib import Path

def compare_banks(applicant,quote,offers,as_of,contexts=None,catalog_path=None):
    path=Path(catalog_path or Path(__file__).resolve().parents[1]/'config/bank_catalog.json')
    catalog=json.loads(path.read_text());fresh=catalog['reviewed_on']<=as_of<=catalog['valid_until']
    quoted={o['bank_code']:o for o in offers};live={c['bank_code']:c for c in (contexts or []) if c.get('status')=='live_extracted'}
    items=[]
    for p in catalog['products']:
        if p['product']!=quote.product: continue
        margin=p.get('asset_margin') if fresh else None;cap=p.get('principal_cap') if fresh else None;months=p.get('max_months') if fresh else None
        planning=p.get('planning_margin') if fresh else None;note=p['note'];source=p['source'];basis='published product ceiling';term_data='reviewed_snapshot' if fresh else 'expired'
        bands=p.get('age_bands',[])
        if bands and fresh:
            band=next((b for b in bands if quote.vehicle_age<=b[0]),None)
            margin=band[1] if band else None;months=band[2] if band else None
            if not band: note='Vehicle age is outside the supported published schedule. Ask the bank.'
        online=live.get(p['bank_code'])
        if online:
            rules=online.get('rules',{})
            if 'margin_asset_only' in rules: margin=rules['margin_asset_only']['value'];planning=None
            if 'max_principal' in rules: cap=rules['max_principal']['value']
            if 'max_months' in rules: months=rules['max_months']['value']
            # An age schedule takes precedence over generic headline margin.
            if online.get('age_bands'):
                band=next((b for b in online['age_bands'] if quote.vehicle_age<=b['upper_age_years']),None)
                margin=band['margin'] if band else None;months=band['max_months'] if band else None
            source=online['sources'][0]['url'];term_data='live_extracted'
        if quote.product=='home' and applicant.housing_loans_count>=2:
            margin=min(margin,.70) if margin is not None else .70;planning=None;basis='BNM third-housing-loan ceiling'
            note='A 70% regulatory ceiling applies when two housing loans are outstanding; the bank may offer less.'
        published_amount=quote.asset_price*margin if margin is not None and quote.product!='personal' else cap
        qoffer=quoted.get(p['bank_code'])
        item={'bank_code':p['bank_code'],'bank':p['bank'],'product':p['product'],'published_margin':margin,
              'combined_margin':p.get('combined_margin') if fresh else None,'planning_margin':planning,
              'published_principal_ceiling_rm':published_amount,'basis':basis,'max_months':months,'source':source,
              'note':note,'term_data_status':term_data,'reviewed_on':catalog['reviewed_on'],
              'personalized_offer':False,'quoted_offer_id':qoffer['offer_id'] if qoffer else None,
              'monthly_payment_rm':qoffer['financials']['monthly_instalment_rm'] if qoffer else None,
              'quoted_annual_rate':qoffer['quotation_summary']['annual_rate'] if qoffer else None,
              'quoted_rate_method':qoffer['quotation_summary']['rate_method'] if qoffer else None,
              'quoted_months':qoffer['quotation_summary']['months'] if qoffer else None,
              'quoted_upfront_fees_rm':qoffer['quotation_summary']['fees_rm'] if qoffer else None,
              'quoted_total_financing_cost_rm':qoffer['financials']['total_financing_cost_rm'] if qoffer else None,
              'effective_cashflow_rate':qoffer['financials']['annual_effective_cashflow_rate'] if qoffer else None,
              'quoted_principal_rm':qoffer['financials']['requested_bank_financing_rm'] if qoffer else None,
              'quoted_margin':quote.requested_principal/quote.asset_price if qoffer and quote.product!='personal' else None,
              'planning_financing_ceiling_rm':qoffer['financials']['illustrative_financing_ceiling_rm'] if qoffer else None,
              'published_reference_rates':online.get('rates',[]) if online else []}
        items.append(item)
    # Quote rates can be ranked; private unquoted borrower rates cannot be guessed.
    return sorted(items,key=lambda x:(x['effective_cashflow_rate'] is None,x['effective_cashflow_rate'] or 0,x['bank']))

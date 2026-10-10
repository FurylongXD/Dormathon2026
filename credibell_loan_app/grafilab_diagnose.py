"""Safe, non-inference connection check. Run from the extracted package folder.

Only known provider error codes and a validated request ID are displayed.
Never prints the key, HTTP error message/body, model list or request headers.
"""
import json
import re
import urllib.error
import urllib.request
from loan_llm.client import GrafilabClient, NoRedirect, ServiceError
from loan_llm.settings import Settings

KNOWN_CODES = {
    "billing_currency_unset", "invalid_api_key", "model_not_found", "insufficient_quota",
    "permission_denied", "access_denied", "forbidden", "server_error", "unauthorized",
}


def error_details(raw, headers, key=""):
    result = {"provider_error_code":None,"request_id":None,"body_format":"other"}
    rid = headers.get("X-Request-Id", "")
    if isinstance(rid,str) and re.fullmatch(r"req_[0-9a-f]{24}",rid) and (not key or key not in rid):
        result["request_id"] = rid
    try:
        value = json.loads(raw)
        result["body_format"] = "json"
        error = value.get("error",{}) if isinstance(value,dict) else {}
        code = error.get("code") if isinstance(error,dict) else None
        if code is None and isinstance(value,dict): code = value.get("code")
        if isinstance(code,str) and code in KNOWN_CODES and (not key or key not in code):
            result["provider_error_code"] = code
    except (ValueError,UnicodeError):
        if raw.lstrip().lower().startswith((b"<!doctype html",b"<html")):
            result["body_format"] = "html"
    return result


def diagnose(settings=None, opener=None):
    settings = settings or Settings.load()
    # Reuse exact HTTPS endpoint validation; never send credentials to another host.
    GrafilabClient(settings)
    key = settings.api_key.strip()
    if not key:
        raise ServiceError("MISSING_KEY","Set your existing key in the backend .env.",400)
    if not key.isascii() or any(c.isspace() for c in key):
        raise ServiceError("INVALID_KEY_FORMAT","The key contains whitespace or unexpected characters.",400)
    req = urllib.request.Request(settings.base_url+"/models",method="GET",
        headers={"Authorization":"Bearer "+key,"Accept":"application/json"})
    opener = opener or urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req,timeout=20) as response:
            response.read(1)  # Availability only; never dump the catalogue.
            return {"http_status":response.status,"connection":"accepted",
                    "next_step":"Run python -m loan_llm models to select an available chat model."}
    except urllib.error.HTTPError as error:
        details = error_details(error.read(16_384),error.headers,key)
        result = {"http_status":error.code,"connection":"rejected",**details}
        if details["provider_error_code"] == "billing_currency_unset":
            result["next_step"] = "Set the correct country in the Grafilab profile of the account that owns this key, save, then retry."
        elif error.code == 403:
            result["next_step"] = "If the owning account already has its country set, ask Grafilab support to investigate this status and request ID. This output does not establish a billing-currency cause."
        elif error.code == 401:
            result["next_step"] = "Check that the existing API key was copied correctly and is still active."
        else:
            result["next_step"] = "Check the provider status with Grafilab support using the request ID if available."
        return result
    except (urllib.error.URLError,OSError,ValueError):
        return {"connection":"failed","error":"NETWORK_OR_TLS_ERROR",
                "next_step":"Check network, firewall/proxy and certificates. HTTPS verification stays enabled."}


if __name__ == "__main__":
    try:
        print(json.dumps(diagnose(),indent=2))
    except ServiceError as error:
        print(json.dumps({"error":error.public()},indent=2))

"""OpenAI-compatible Grafilab HTTP client, with safe actionable errors."""
import json
import socket
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlparse
from .settings import Settings


class ServiceError(Exception):
    def __init__(self, code, message, status=503):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)

    def public(self):
        return {"code": self.code, "message": self.message}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GrafilabClient:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or Settings.load()
        p = urlparse(self.settings.base_url)
        if (p.scheme != "https" or p.hostname != "llm.grafilab.ai" or p.path.rstrip("/") != "/v1"
                or p.username or p.password or p.query or p.fragment or p.port not in {None, 443}):
            raise ServiceError("INVALID_ENDPOINT", "Use https://llm.grafilab.ai/v1.", 400)
        self.transport = transport or self._http

    def _http(self, method, path, payload):
        key = self.settings.api_key.strip()
        if not key:
            raise ServiceError("MISSING_KEY", "Set your existing GRAFILAB_API_KEY in the backend .env or environment.")
        if any(c.isspace() for c in key):
            raise ServiceError("INVALID_KEY_FORMAT", "Reenter the API key without spaces or line breaks.")
        data = json.dumps(payload, allow_nan=False).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(self.settings.base_url + path, data=data, method=method,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=40) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ServiceError("RESPONSE_TOO_LARGE", "Grafilab returned an oversized response.")
            return json.loads(raw)
        except urllib.error.HTTPError as error:
            errors = {
                400: ("REQUEST_REJECTED", "Grafilab rejected the request; confirm the model supports chat completions."),
                401: ("AUTH_REJECTED", "Grafilab rejected authentication. Check your existing key."),
                403: ("ACCESS_REJECTED", "Check Grafilab account permissions and your profile billing currency."),
                404: ("MODEL_OR_ROUTE_NOT_FOUND", "Check /models for the exact available model ID and verify the base URL."),
                402: ("CREDIT_REQUIRED", "Check your Grafilab credit balance."),
                429: ("QUOTA_OR_RATE_LIMIT", "Check your Grafilab credits and usage limits; insufficient credits can return HTTP 429.")}
            code, message = errors.get(error.code, ("PROVIDER_HTTP_ERROR", "Grafilab returned an HTTP error; retry later or check service status."))
            # HTTP response bodies may contain echoed request data: do not expose them.
            raise ServiceError(code, f"HTTP {error.code}: {message}") from None
        except urllib.error.URLError as error:
            if isinstance(error.reason, ssl.SSLError):
                code, message = "TLS_ERROR", "HTTPS certificate verification failed. Check certificates/proxy; do not disable verification."
            elif isinstance(error.reason, socket.gaierror):
                code, message = "DNS_ERROR", "Could not resolve llm.grafilab.ai. Check your internet connection and DNS."
            else:
                code, message = "CONNECTION_ERROR", "Could not connect to Grafilab. Check your network, firewall or proxy."
            raise ServiceError(code, message) from None
        except TimeoutError:
            raise ServiceError("TIMEOUT", "Grafilab did not respond within 40 seconds.") from None
        except OSError:
            raise ServiceError("CONNECTION_ERROR", "The HTTPS connection to Grafilab failed.") from None
        except (ValueError, UnicodeError):
            raise ServiceError("INVALID_PROVIDER_JSON", "Grafilab did not return valid JSON.") from None

    def models(self):
        reply = self.transport("GET", "/models", None)
        try:
            values = [{"id": str(row["id"])} for row in reply["data"]]
        except (KeyError, TypeError):
            raise ServiceError("INVALID_MODEL_LIST", "Grafilab returned an unexpected model catalogue.") from None
        return {"models": values, "configured_model": self.settings.model or None,
            "configured_model_available": bool(self.settings.model) and any(
                row["id"].casefold() == self.settings.model.casefold() for row in values)}

    def complete(self, system_prompt, context, max_tokens=1800):
        if not self.settings.model:
            raise ServiceError("MISSING_MODEL", "Set GRAFILAB_MODEL to an exact chat model ID from your /models list.")
        reply = self.transport("POST", "/chat/completions", {
            "model": self.settings.model, "temperature": 0, "max_tokens": max_tokens, "stream": False,
            "messages": [{"role": "system", "content": system_prompt},
                         {"role": "user", "content": json.dumps(context, allow_nan=False)}]})
        try:
            raw = reply["choices"][0]["message"]["content"]
            if not isinstance(raw, str) or len(raw) > 20000:
                raise ValueError()
            raw = raw.strip()
            if raw.startswith("```json") and raw.endswith("```"):
                raw = raw[7:-3].strip()
            elif raw.startswith("```") and raw.endswith("```"):
                raw = raw[3:-3].strip()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise ServiceError("INVALID_LLM_OUTPUT", "The model did not return the required structured JSON.") from None
        usage = reply.get("usage", {})
        safe_usage = {k: int(usage[k]) for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                      if isinstance(usage, dict) and isinstance(usage.get(k), int) and usage[k] >= 0}
        return value, {"model": self.settings.model, "usage": safe_usage}

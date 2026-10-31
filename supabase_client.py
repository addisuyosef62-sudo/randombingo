import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SupabaseError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def supabase_request(method, path, body=None, prefer=None):
    project_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not project_url or not service_key:
        raise SupabaseError("Supabase server credentials are not configured.")

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        f"{project_url}/rest/v1/{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            response_body = response.read()
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise SupabaseError(
            f"Supabase request failed ({exc.code}): {error_body}",
            status_code=exc.code,
        ) from exc
    except URLError as exc:
        raise SupabaseError(f"Could not reach Supabase: {exc.reason}") from exc

    if not response_body:
        return None
    return json.loads(response_body)

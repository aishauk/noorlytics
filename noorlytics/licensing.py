import hashlib, json, os, platform, time
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from socket import timeout as SocketTimeout

from .logger import log_to_console

LICENSE_SERVER = os.getenv("NOOR_LICENSE_SERVER", "https://noor-license.onrender.com")
TIMEOUT = float(os.getenv("NOOR_LICENSE_TIMEOUT", "15"))


def ensure_license_server_up(timeout: float | None = None) -> dict:
    """Lightweight health check so we fail fast before consuming a run.

    Returns a dict with at least {"ok": bool, "error"|"status": str}.
    """
    if timeout is None:
        timeout = TIMEOUT
    url = f"{LICENSE_SERVER}/health"
    req = Request(url, method="GET")
    log_to_console(f"🔎 License server health check: {url} (timeout={timeout}s)")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
            return {"ok": True, "status": data.get("status", "unknown")}
    except HTTPError as e:
        return {"ok": False, "error": f"http {e.code}"}
    except (URLError, TimeoutError, SocketTimeout):
        log_to_console(f"⚠️ License server health check timed out after {timeout}s")
        return {"ok": False, "error": "license_server_timeout"}


def device_fingerprint() -> str:
    base = f"{platform.system()}|{platform.node()}|{platform.processor()}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]

def check_and_consume(license_key: str, product: str, consume: bool = True) -> dict:
    payload = {
        "license_key": license_key.strip(),
        "product": product,
        "device": device_fingerprint(),
        "consume": consume,
        "ts": int(time.time()),
        "version": os.getenv("NOOR_VERSION", "0.1.0"),
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        f"{LICENSE_SERVER}/issue",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    log_to_console(f"🔐 Sending license request to {LICENSE_SERVER}/issue (timeout={TIMEOUT}s)")
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return {"ok": False, "error": f"http {e.code}"}
    except (URLError, TimeoutError, SocketTimeout):
        log_to_console(f"⚠️ License server did not respond within {TIMEOUT}s")
        return {"ok": False, "error": "license_server_timeout"}


def require_valid_license(license_key: str, product: str):
    """
    Check license before running a command.
    Exits the program if license is invalid or quota exhausted.
    """
    result = check_and_consume(license_key, product)
    if not result.get("ok"):
        error = result.get("error", "unknown_error")
        remaining = result.get("remaining", "?")
        if error == "free_runs_exhausted":
            print(f"❌ Free plan limit reached. Remaining: 0")
        elif error == "device_mismatch":
            print(f"❌ License is already bound to another device.")
        elif error == "http 401":
            print(f"❌ Invalid license key.")
        elif error == "license_server_unreachable":
            print(f"❌ Could not reach license server.")
        else:
            print(f"❌ License check failed: {error} (remaining={remaining})")
        sys.exit(1)

    plan = result.get("plan", "unknown")
    remaining = result.get("remaining", "?")
    print(f"✅ License OK (plan={plan}, remaining≈{remaining})")

def require_license_or_exit(product: str, license_key: str | None = None):
    """
    Check license before running a command.
    - Hämtar key från argument eller NOOR_LICENSE_KEY env var.
    - Avslutar programmet med ett tydligt felmeddelande om något är fel.
    """
    # 1) Hämta licensnyckel
    key = (license_key or "").strip() or os.getenv("NOOR_LICENSE_KEY", "").strip()
    if not key:
        print("❌ No license key provided. Set NOOR_LICENSE_KEY or use --license-key.", file=sys.stderr)
        sys.exit(1)

    # 2) Kolla med servern
    result = check_and_consume(key, product, consume=True)

    if not result.get("ok"):
        error = result.get("error", "unknown_error")
        remaining = result.get("remaining")

        if error == "free_runs_exhausted":
            print("❌ Free plan limit reached (no runs remaining). Upgrade to Pro to continue.", file=sys.stderr)
        elif error == "device_mismatch":
            print("❌ License is already bound to another device.", file=sys.stderr)
        elif error.startswith("http "):
            print(f"❌ License server returned an HTTP error: {error}", file=sys.stderr)
        elif error == "license_server_unreachable":
            print("❌ Could not reach license server. Check your network connection.", file=sys.stderr)
        else:
            print(f"❌ License check failed: {error} (remaining={remaining})", file=sys.stderr)
        sys.exit(1)

    # 3) Snygg liten bekräftelse
    plan = result.get("plan", "unknown")
    remaining = result.get("remaining")
    if remaining is not None:
        print(f"✅ License OK (plan={plan}, remaining≈{remaining})")
    else:
        print(f"✅ License OK (plan={plan})")

def get_license_status() -> dict:
    """Return license status without consuming a run."""
    key = os.getenv("NOOR_LICENSE_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "no_license_key"}

    # Health check
    health = ensure_license_server_up()
    if not health.get("ok"):
        return {"ok": False, "error": health.get("error")}

    # Ask for status (consume=False)
    result = check_and_consume(key, product="status", consume=False)

    return result

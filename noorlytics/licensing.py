import hashlib, json, os, platform, time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

LICENSE_SERVER = os.getenv("NOOR_LICENSE_SERVER", "http://127.0.0.1:9000")
TIMEOUT = 5

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
    req = Request(f"{LICENSE_SERVER}/issue", data=data, headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return {"ok": False, "error": f"http {e.code}"}
    except URLError:
        return {"ok": False, "error": "license_server_unreachable"}
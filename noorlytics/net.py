# noorlytics/net.py
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .settings import get_settings

_session = None

def session() -> requests.Session:
    global _session
    if _session is None:
        s = get_settings()
        sess = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=16,
            pool_maxsize=16,
            max_retries=Retry(total=0, backoff_factor=0),
        )
        sess.mount("http://", adapter)
        sess.mount("https://", adapter)
        _session = sess
    return _session

def timeout() -> float:
    return get_settings().http_timeout
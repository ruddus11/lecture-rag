"""compose live와 모델·검색엔진 ready를 구분한다. 로그에 비밀을 기록하지 않는다."""

import json
import time
from urllib.error import URLError
from urllib.request import urlopen

url = "http://127.0.0.1:8000/api/v1/health/ready"
deadline = time.monotonic() + 600
while time.monotonic() < deadline:
    try:
        with urlopen(url, timeout=10) as response:
            body = json.load(response)
        if body["status"] == "ok":
            print(json.dumps(body, ensure_ascii=False))
            break
    except (URLError, TimeoutError):
        pass
    time.sleep(5)
else:
    raise SystemExit("readiness failed after 600 seconds; inspect compose logs")

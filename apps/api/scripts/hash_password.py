"""bcrypt 해시 생성: uv run python -m scripts.hash_password '<비밀번호>'"""

import sys

from app.core.auth import hash_password

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m scripts.hash_password '<password>'")
    print(hash_password(sys.argv[1]))

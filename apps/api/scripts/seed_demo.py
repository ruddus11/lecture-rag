"""yaml → 기관·사용자·컬렉션 upsert. 기존 컬렉션 version 은 유지한다.

docker compose exec api python -m scripts.seed_demo
"""

from app.core.config import get_settings
from app.storage.db import Database
from app.storage.seed import seed_from_files

if __name__ == "__main__":
    s = get_settings()
    db = Database(s.db_url)
    db.create_all()
    print(seed_from_files(db, s.institutions_file, s.users_file))

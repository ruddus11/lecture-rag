"""The packaged OpenSearch adapter must import from a shallow container path."""

from pathlib import Path
from typing import Any

from app.retrieval import keyword


def test_keyword_adapter_imports_from_container_layout():
    source = Path(keyword.__file__).read_text()
    container_file = "/app/app/retrieval/keyword.py"
    namespace: dict[str, Any] = {"__name__": "container_keyword", "__file__": container_file}

    exec(compile(source, container_file, "exec"), namespace)

    assert callable(namespace["index_body_korean"])

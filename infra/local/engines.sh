#!/bin/zsh
# 로컬 검증용 Qdrant·OpenSearch 기동/중지 (README.md 참고). 127.0.0.1 에만 바인딩한다.
set -e
R="${0:A:h:h:h}"
T="$R/.tools"
E="$T/e2e"
mkdir -p "$E"
case "${1:-start}" in
  start)
    cd "$E"  # qdrant 는 작업 폴더에 .qdrant-initialized 를 만든다
    QDRANT__SERVICE__HOST=127.0.0.1 QDRANT__STORAGE__STORAGE_PATH="$E/qdrant_storage" \
      QDRANT__STORAGE__SNAPSHOTS_PATH="$E/qdrant_snapshots" QDRANT__TELEMETRY_DISABLED=true \
      nohup "$T/qdrant/qdrant" > "$E/qdrant.log" 2>&1 &
    export OPENSEARCH_JAVA_HOME="$(echo $T/opensearch/jdk-21*/Contents/Home)" OPENSEARCH_JAVA_OPTS="-Xms1g -Xmx1g"
    nohup "$T/opensearch/opensearch-2.19.7/bin/opensearch" -Ediscovery.type=single-node -Enetwork.host=127.0.0.1 \
      -Epath.data="$E/os_data" -Epath.logs="$E/os_logs" > "$E/opensearch.log" 2>&1 &
    for i in {1..90}; do curl -sf localhost:9200/_cluster/health >/dev/null && break; sleep 2; done
    curl -s -XPUT localhost:9200/_cluster/settings -H 'content-type: application/json' \
      -d '{"persistent":{"cluster.routing.allocation.disk.threshold_enabled":false}}' >/dev/null
    curl -s localhost:6333/readyz; echo; curl -s "localhost:9200/_cat/plugins"
    ;;
  stop)
    pkill -f "$T/qdrant/qdrant" || true
    pkill -f "opensearch-2.19.7" || true
    ;;
esac

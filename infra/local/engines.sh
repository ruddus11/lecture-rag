#!/bin/zsh
# 로컬 검증용 Qdrant·OpenSearch 기동/중지 (README.md 참고). 127.0.0.1 에만 바인딩한다.
# 포트는 QDRANT_PORT(기본 6333, gRPC는 +1)·OPENSEARCH_PORT(기본 9200, transport는 +100)로 바꿀 수 있다.
set -e
QP="${QDRANT_PORT:-6333}" OP="${OPENSEARCH_PORT:-9200}"
R="${0:A:h:h:h}"
T="$R/.tools"
E="$T/e2e"
mkdir -p "$E"
case "${1:-start}" in
  start)
    cd "$E"  # qdrant 는 작업 폴더에 .qdrant-initialized 를 만든다
    QDRANT__SERVICE__HOST=127.0.0.1 QDRANT__STORAGE__STORAGE_PATH="$E/qdrant_storage" \
      QDRANT__STORAGE__SNAPSHOTS_PATH="$E/qdrant_snapshots" QDRANT__TELEMETRY_DISABLED=true \
      QDRANT__SERVICE__HTTP_PORT=$QP QDRANT__SERVICE__GRPC_PORT=$((QP + 1)) \
      nohup "$T/qdrant/qdrant" > "$E/qdrant.log" 2>&1 &
    echo $! > "$E/qdrant.pid"
    export OPENSEARCH_JAVA_HOME="$(echo $T/opensearch/jdk-21*/Contents/Home)" OPENSEARCH_JAVA_OPTS="-Xms1g -Xmx1g"
    nohup "$T/opensearch/opensearch-2.19.7/bin/opensearch" -Ediscovery.type=single-node -Enetwork.host=127.0.0.1 \
      -Epath.data="$E/os_data" -Epath.logs="$E/os_logs" -Ehttp.port=$OP -Etransport.port=$((OP + 100)) \
      > "$E/opensearch.log" 2>&1 &
    echo $! > "$E/opensearch.pid"
    for i in {1..90}; do curl -sf localhost:$OP/_cluster/health >/dev/null && break; sleep 2; done
    curl -s -XPUT localhost:$OP/_cluster/settings -H 'content-type: application/json' \
      -d '{"persistent":{"cluster.routing.allocation.disk.threshold_enabled":false}}' >/dev/null
    curl -s localhost:$QP/readyz; echo; curl -s "localhost:$OP/_cat/plugins"
    ;;
  stop)
    # 이 작업트리가 띄운 프로세스만 멈춘다 (다른 작업트리의 같은 바이너리는 건드리지 않음)
    for n in qdrant opensearch; do [[ -f "$E/$n.pid" ]] && { kill "$(cat "$E/$n.pid")" 2>/dev/null || true; rm -f "$E/$n.pid"; }; done
    ;;
esac

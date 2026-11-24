#!/usr/bin/env bash
# HBase for the `hbase` profile (Task 8): the standalone master (regionserver and ZooKeeper in the same JVM) in
# the foreground, and next to it the Thrift server on port 9090 that happybase uses. When either process ends,
# the other is stopped and the container exits with its status, so `docker compose ps` shows the failure and the
# restart policy brings HBase back. `docker compose stop` (SIGTERM) shuts both down cleanly.
set -u

hbase master start &
master=$!
hbase thrift start -p 9090 &
thrift=$!

trap 'kill -TERM "$master" "$thrift" 2>/dev/null' TERM INT

wait -n "$master" "$thrift"
status=$?
kill -TERM "$master" "$thrift" 2>/dev/null
wait
exit "$status"

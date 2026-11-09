#!/usr/bin/env bash
# Checks the running stack. Run from anywhere (bash; Git Bash on Windows) after
#   docker compose --profile core up -d        (and --profile yarn for the YARN checks)
# Prints one line per check, "OK <name>" or "FAIL <name>: <first error line>", and exits 1 if any check failed.
set -uo pipefail
# With pipefail, a pipeline must not end in "grep -q": grep exits at the first match, the command feeding it then
# fails writing to the closed pipe, and the check fails at random. Use "grep ... >/dev/null", which reads to the end.
cd "$(dirname "$0")"
export MSYS_NO_PATHCONV=1 # Git Bash: don't rewrite /lake, /tmp, ... into Windows paths

log=$(mktemp)
trap 'rm -f "$log"' EXIT
failed=0

client() { docker compose exec -T client "$@"; }
py() { client python3 -c "$1"; }
beeline() {
  docker compose exec -T hiveserver2 beeline -u jdbc:hive2://localhost:10000 -n hive \
    --silent=true --outputformat=tsv2 --showHeader=false -e "$1" 2>/dev/null
}

run() { # run <name> <function>
  local name=$1 line
  if "$2" >"$log" 2>&1; then
    echo "OK $name"
  else
    line=$(grep -m1 -E 'Error|ERROR|Exception|FAIL|error:|Assertion' "$log")
    [ -n "$line" ] || line=$(grep -v '^[[:space:]]*$' "$log" | tail -n1)
    echo "FAIL $name: ${line:-no output (is the service running?)}"
    failed=1
  fi
}

wait_ready() { # right after "up -d" the services are still starting: retry, and keep the last error for the FAIL line
  local i
  for i in $(seq 1 30); do # the NameNode refuses connections for its first seconds; safemode wait doesn't retry that
    client hdfs dfsadmin -safemode wait >"$log.ready" 2>&1 && break
    [ "$i" = 30 ] && { echo "namenode not reachable within 2.5 minutes: $(grep -m1 -E 'safemode:|Exception|refused' "$log.ready" || grep -v WARN "$log.ready" | tail -n1)"; rm -f "$log.ready"; return 1; }
    sleep 5
  done
  rm -f "$log.ready"
  for _ in $(seq 1 60); do # HiveServer2 needs a minute or two after "up -d"
    beeline "SELECT 1;" | grep -x 1 >/dev/null && return 0
    sleep 5
  done
  echo "hiveserver2 did not answer within 5 minutes"
  return 1
}

check_hdfs() {
  client hdfs dfs -mkdir -p /lake/raw /lake/clean /lake/dw && client hdfs dfs -ls /lake | grep '/lake/dw$' >/dev/null
}

check_hive() {
  beeline "SHOW DATABASES;" | grep -x default >/dev/null
}

check_spark() {
  py "
from common.spark import get_spark
s = get_spark('check')
s.range(10).write.mode('overwrite').orc('/tmp/check_orc')
n = s.read.orc('/tmp/check_orc').count()
assert n == 10, f'read {n} rows'
"
}

check_metastore() {
  py "
from common.spark import get_spark
s = get_spark('check')
s.sql('DROP TABLE IF EXISTS default.check_rt')
s.sql('CREATE TABLE default.check_rt STORED AS ORC AS SELECT id FROM range(10)')
" || return 1
  local n
  n=$(beeline "SELECT COUNT(*) FROM default.check_rt;" | tr -d '[:space:]')
  [ "$n" = 10 ] || { echo "Error: beeline counted '$n' rows in the Spark table check_rt"; return 1; }
  beeline "DROP TABLE IF EXISTS default.check_rt2;
           CREATE TABLE default.check_rt2 (x INT) STORED AS ORC;
           INSERT INTO default.check_rt2 VALUES (1), (2);" >/dev/null || {
    echo "Error: beeline could not create check_rt2"
    return 1
  }
  py "
from common.spark import get_spark
n = get_spark('check').table('default.check_rt2').count()
assert n == 2, f'Spark read {n} rows of the Hive table check_rt2'
" || return 1
  beeline "DROP TABLE default.check_rt2;" >/dev/null
}

check_yarn() {
  client env SPARK_MASTER=yarn python3 -c "
from common.spark import get_spark
n = get_spark('check-yarn', hive=False).range(100).count()
assert n == 100, f'counted {n}'
" || return 1
  client bash -c "printf 'big data lake\nbig lake\nlake\n' | hdfs dfs -put -f - /tmp/check_wc.txt" || return 1
  client python3 docker/check_wordcount.py -r hadoop hdfs:///tmp/check_wc.txt >"$log.wc" 2>&1
  local rc=$?
  if [ $rc -ne 0 ] || ! grep -q $'"lake"\t3' "$log.wc"; then
    grep -m1 -E 'Error|Exception' "$log.wc" || echo "Error: mrjob word count gave no \"lake\" 3"
    rm -f "$log.wc"
    return 1
  fi
  rm -f "$log.wc"
}

check_hive_yarn() {
  local n
  n=$(beeline "SET mapreduce.framework.name=yarn;
               SET hive.compute.query.using.stats=false;
               SELECT COUNT(*) FROM default.check_rt;" | tr -d '[:space:]')
  [ "$n" = 10 ] || { echo "Error: Hive on YARN counted '$n' rows"; return 1; }
}

cleanup() {
  beeline "DROP TABLE IF EXISTS default.check_rt; DROP TABLE IF EXISTS default.check_rt2;" >/dev/null
  client hdfs dfs -rm -r -f -skipTrash /tmp/check_orc /tmp/check_wc.txt >/dev/null 2>&1
}

if ! wait_ready >"$log" 2>&1; then
  echo "FAIL stack: not ready ($(grep -v '^[[:space:]]*$' "$log" | tail -n1)); is 'docker compose --profile core up -d' running?"
  exit 1
fi

run hdfs check_hdfs
run hive check_hive
run spark check_spark
run metastore check_metastore
if docker compose ps --status running --services 2>/dev/null | grep -x resourcemanager >/dev/null; then
  run yarn check_yarn
  run hive-yarn check_hive_yarn
fi
cleanup
exit $failed

# Docker Stack

Every member runs the same HDFS, Hive, Spark and (on demand) YARN in Docker. All project code, tests and tools run in the `client` container. Nothing else is installed on your laptop.

Task 8 extends the stack with HBase, Spark Thrift Server and Zeppelin:

- `hbase` profile: HBase and its Thrift interface.
- `zeppelin` profile: Spark Thrift Server and Zeppelin notebooks.

See [SETUP.md](SETUP.md) for platform-specific setup instructions and which profiles your area needs.

## Prerequisites

- Docker Desktop with sufficient memory:
  - Core: approximately 4.5 GB.
  - Core + HBase: approximately 5.5 GB.
  - Core + Zeppelin: approximately 7 GB.
  - Core + HBase + Zeppelin: approximately 8 GB.
  - Core + YARN: approximately 7.5 GB.
- Git; on Windows also Git Bash (for `check.sh`). Clone the repository anywhere.
- About 10 GB of free disk for images and volumes, about 15 GB more for the `zeppelin` profile (the official Zeppelin image alone is about 14 GB on disk); allow 20 GB more when generating the 10× dataset.

For platform-specific memory configuration, see [SETUP.md](SETUP.md).

## Start, Stop and Reset

Run these commands from this `docker/` folder.

| What | Command |
|---|---|
| Start the core stack (HDFS, Hive, client) | `docker compose --profile core up -d` |
| Also start YARN (MapReduce, Spark on YARN, Hive on YARN) | `docker compose --profile core --profile yarn up -d` |
| Start HBase | `docker compose --profile core --profile hbase up -d` |
| Start Zeppelin and Spark Thrift Server (dashboards) | `docker compose --profile core --profile zeppelin up -d` |
| Zeppelin with HBase (search notebook) | `docker compose --profile core --profile hbase --profile zeppelin up -d` |
| Check that everything works | `./check.sh` (Git Bash on Windows) |
| Stop the core and YARN profiles, keeping data | `docker compose --profile core --profile yarn down` |
| Stop all profiles, keeping data | `docker compose --profile core --profile yarn --profile hbase --profile zeppelin down` |
| Stop and delete all data (HDFS, metastore and HBase data) | `docker compose --profile core --profile yarn --profile hbase --profile zeppelin down -v` |
| Rebuild images after a change in `stack/`, `hive/`, `zeppelin/` or `requirements.txt` | Re-run the original build command with the profiles you use, for example: `docker compose --profile core build --build-arg APACHE_MIRROR=https://dlcdn.apache.org` |

The first start builds the images `isit312/stack:1.0` (Hadoop, Spark, HBase, Python) and `isit312/hive:1.0` (about 15 minutes, downloads about 2 GB); the `zeppelin` profile also builds `isit312/zeppelin:1.0` (downloads about 2.5 GB more and takes about 14 GB on disk: `apache/zeppelin:0.11.2` bundles conda Python and R environments).

The build takes Hadoop, Spark and HBase from `archive.apache.org`. If that is slow, build with a faster mirror that still has these versions:

```bash
docker compose --profile core build --build-arg APACHE_MIRROR=https://dlcdn.apache.org
```

Rebuild with the same mirror every time. A different `APACHE_MIRROR` value invalidates Docker's build cache, so Hadoop and Spark are downloaded again. With the same value, an unchanged rebuild takes seconds.

To see which mirror your image used:

```bash
docker history --no-trunc isit312/stack:1.0 | grep -o 'APACHE_MIRROR=[^ ]*' | head -1
```

Rebuild after every rebase that brings new commits affecting the Docker images.

PySpark in the image comes from the Spark distribution itself (`PYTHONPATH` points at `/opt/spark/python/lib/pyspark.zip` and its Py4J zip), so the build doesn't download the PySpark package a second time. `requirements.txt` still pins `pyspark==3.5.9` for a host virtual environment, which is only for editor completion.

## Automated Checks

`check.sh` waits until HiveServer2 answers (usually a minute or two after `up -d`), then runs the available checks.

Example output when the core, HBase and Zeppelin profiles are running:

```text
OK hdfs
OK hive
OK spark
OK metastore
SKIP yarn
SKIP hive-yarn
OK sparksql
OK hbase
OK zeppelin
```

Checks include:

- `hdfs`: creates and verifies the project HDFS directories.
- `hive`: checks Hive database access.
- `spark`: writes and reads ORC data using Spark.
- `metastore`: verifies that Hive and Spark share the metastore.
- `yarn` and `hive-yarn`: Spark on YARN, an mrjob word count, and a Hive query on YARN, when the `yarn` profile runs.
- `sparksql`: checks Spark Thrift Server database access when available.
- `hbase`: creates a test table, writes a row, reads it back and deletes the table when available.
- `zeppelin`: checks that the Zeppelin API responds when available.

A successful check prints `OK <name>`. A check whose profile isn't running prints `SKIP <name>`. A failed check prints `FAIL <name>: <first error line>` and the script exits with status 1.

## Services and Ports

| Service | Profile | What | Host port |
|---|---|---|---|
| `namenode` | core | HDFS NameNode | 9870 (web UI), 8020 |
| `datanode` | core | HDFS DataNode | 9864 |
| `metastore` | core | Hive metastore 3.1.3 (Derby in the volume `hive_metastore_db`) | 9083 |
| `hiveserver2` | core | HiveServer2 3.1.3 with the stack's Hadoop 3.3.6 client; MapReduce in local mode | 10000 (JDBC), 10002 (web UI) |
| `client` | core | Python 3.10, Spark 3.5.9, Hadoop client, repository mounted at `/repo` | 4040 (Spark UI) |
| `resourcemanager` | yarn | YARN ResourceManager | 8088 (web UI) |
| `nodemanager` | yarn | YARN NodeManager (2 GB for containers) | 8042 |
| `historyserver` | yarn | MapReduce job history | 19888 |
| `hbase` | hbase | HBase 2.5 standalone (master, regionserver, ZooKeeper) over HDFS, plus the Thrift server for happybase | 16010 (web UI), 9090 (Thrift) |
| `sparksql` | zeppelin | Spark Thrift Server (Spark SQL over JDBC, same metastore as Hive) | 10001 (JDBC), 4041 (Spark UI) |
| `zeppelin` | zeppelin | Zeppelin 0.11.2 with the interpreters `%hive`, `%sparksql` and `%python`; notebooks in the repo's `notebooks/` | 8080 (web UI) |

Data lives in the named volumes `hdfs_nn`, `hdfs_dn` and `hive_metastore_db` (HBase keeps its tables in HDFS under `/hbase`): `down` keeps it, `down -v` deletes it.

## Working in the client container
- Shell: `docker compose exec client bash` (you are in `/repo`, the repo on your laptop; edits on either side are
  the same files).
- Unit tests (no data needed): `docker compose exec client pytest -m "not integration"`; your area:
  `docker compose exec client pytest tests/<area>`; after a full pipeline run: `pytest -m integration`.
- Lint: `docker compose exec client ruff check .` and `docker compose exec client ruff format --check .`
- Run a module: `docker compose exec client python -m generators.bank` (any module of the repo).
- HDFS: `docker compose exec client hdfs dfs -ls /lake`; web UI http://localhost:9870.
- Spark: `common.spark.get_spark("name")` gives a session with Hive support (local, all cores). For YARN:
  `docker compose exec -e SPARK_MASTER=yarn client python ...` with the `yarn` profile running.
- Hive (beeline): `docker compose exec hiveserver2 beeline -u jdbc:hive2://localhost:10000 -n hive`.
  A query that needs YARN instead of local mode: `SET mapreduce.framework.name=yarn;` first (its tasks run on
  the Java 8 in the stack image: Hive 3.1 doesn't run on Java 11; set in `conf/hive-site.xml`).
- MapReduce with mrjob: `docker compose exec client python <job>.py -r hadoop hdfs:///<input>` (yarn profile).
- HBase: from Python `happybase.Connection("hbase", 9090)` in the client; shell
  `docker compose exec hbase hbase shell` (hbase profile).
- Spark SQL over JDBC: `docker compose exec client beeline -u jdbc:hive2://sparksql:10001 -n hadoop`
  (zeppelin profile).
- Zeppelin: http://localhost:8080 (no login). The interpreters are set in `zeppelin/interpreter.json`; the
  container copies it at every start, so change the file in the repo and restart the `zeppelin` service
  (settings changed in the Zeppelin UI are lost when the container is recreated).

## Memory tips
- `core` needs about 4.5 GB, `yarn` about 3 GB more, `hbase` 1 GB and `zeppelin` 2.5 GB (Spark Thrift Server and
  Zeppelin). Start the extra profiles only when you need them, and stop them afterwards, e.g.
  `docker compose stop resourcemanager nodemanager historyserver`.
- If containers restart or a job dies without an error, give Docker more memory (see Prerequisites) or close other
  programs.
- `docker stats` shows what each container uses.

## Troubleshooting
| Problem | Fix |
|---|---|
| `check.sh: bad interpreter` or `$'\r': command not found` | the file got Windows line endings (an editor saved it with CRLF; `.gitattributes` keeps it LF in Git): `git checkout -- docker/check.sh` |
| `port is already allocated` | another program uses that port; stop it, or change the left side of the port in `docker-compose.yml` locally |
| HiveServer2 not answering | wait two minutes; then `docker compose logs hiveserver2 --tail 50` |
| Metastore errors after an interrupted first start | `docker compose --profile core down -v` and start again (deletes the data) |
| `hbase`, `sparksql` or `zeppelin` not working | `docker compose --profile core --profile hbase --profile zeppelin logs <service> --tail 50`; HBase needs about a minute after `up -d` |
| Docker runs out of disk space | `docker system df` shows what uses it; `docker builder prune` removes old build cache. On Windows the disk file only shrinks after compaction (see [SETUP.md](SETUP.md)) |
| Apple Silicon Mac | `apache/hive:3.1.3` and `apache/zeppelin:0.11.2` exist only for amd64: enable "Use Rosetta for x86/amd64 emulation" in Docker Desktop; they are slower there |

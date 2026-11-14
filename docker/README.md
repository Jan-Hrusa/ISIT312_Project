# Docker Stack

Every member runs the same HDFS, Hive, Spark and (on demand) YARN in Docker. All project code, tests and tools run in the `client` container. Nothing else is installed on your laptop.

Task 8 extends the stack with HBase, Spark Thrift Server and Zeppelin:

- `hbase` profile: HBase and its Thrift interface.
- `zeppelin` profile: Spark Thrift Server and Zeppelin notebooks.

See [SETUP.md](SETUP.md) for platform-specific setup instructions.

## Prerequisites

- Docker Desktop with sufficient memory:
  - Core: approximately 4.5 GB.
  - Core + HBase: approximately 5.5 GB.
  - Core + HBase + Zeppelin: approximately 8 GB.
  - Core + YARN: approximately 7.5 GB.
- Git; on Windows also Git Bash (for `check.sh`). Clone the repository anywhere.
- About 10 GB of free disk for images and volumes; allow 20 GB when generating the 10× dataset.

For platform-specific memory configuration, see [SETUP.md](SETUP.md).

## Start, Stop and Reset

Run these commands from this `docker/` folder.

| What | Command |
|---|---|
| Start the core stack (HDFS, Hive, client) | `docker compose --profile core up -d` |
| Also start YARN (MapReduce, Spark on YARN, Hive on YARN) | `docker compose --profile core --profile yarn up -d` |
| Start HBase | `docker compose --profile core --profile hbase up -d` |
| Start Zeppelin and Spark Thrift Server | `docker compose --profile core --profile hbase --profile zeppelin up -d` |
| Check that everything works | `./check.sh` (Git Bash on Windows) |
| Stop the core and YARN profiles, keeping data | `docker compose --profile core --profile yarn down` |
| Stop all profiles, keeping data | `docker compose --profile core --profile yarn --profile hbase --profile zeppelin down` |
| Stop and delete all data (HDFS, metastore and HBase data) | `docker compose --profile core --profile yarn --profile hbase --profile zeppelin down -v` |
| Rebuild images after a change in `stack/`, `hive/` or `requirements.txt` | Re-run the original build command, for example: `docker compose --profile core build --build-arg APACHE_MIRROR=https://dlcdn.apache.org` |

The first start builds the images `isit312/stack:1.0` (Hadoop, Spark, Python) and `isit312/hive:1.0` (about 15 minutes, downloads about 2 GB).

The build takes Hadoop and Spark from `archive.apache.org`. If that is slow, build with a faster mirror that still has these versions:

```bash
docker compose --profile core build --build-arg APACHE_MIRROR=https://dlcdn.apache.org
```

Rebuild with the same mirror every time. A different `APACHE_MIRROR` value invalidates Docker's build cache, so Hadoop and Spark are downloaded again. With the same value, an unchanged rebuild takes seconds.

To see which mirror your image used:

```bash
docker history --no-trunc isit312/stack:1.0 | grep -o 'APACHE_MIRROR=[^ ]*' | head -1
```

Rebuild after every rebase that brings new commits affecting the Docker images.

## Automated Checks

`check.sh` waits until HiveServer2 answers (usually a minute or two after `up -d`), then runs the available checks.

Example output when the core, HBase and Zeppelin profiles are running:

```text
OK hdfs
OK hive
OK spark
OK metastore
OK sparksql
OK hbase
OK zeppelin
SKIP yarn
SKIP hive-yarn
```

Checks include:

- `hdfs`: creates and verifies the project HDFS directories.
- `hive`: checks Hive database access.
- `spark`: writes and reads ORC data using Spark.
- `metastore`: verifies that Hive and Spark share the metastore.
- `sparksql`: checks Spark Thrift Server database access when available.
- `hbase`: creates a test table, writes a row, reads it back and deletes the table when available.
- `zeppelin`: checks that the Zeppelin API responds when available.
- `yarn` and `hive-yarn`: optional YARN checks.

A successful check prints `OK <name>`. An unavailable optional service prints `SKIP <name>`. A failed check prints `FAIL <name>: <first error line>` and the script exits with status 1.

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
| `h
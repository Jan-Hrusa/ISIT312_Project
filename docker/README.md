# Docker stack

Every member runs the same HDFS, Hive, Spark and (on demand) YARN in Docker; all project code, tests and tools run
in the `client` container. Nothing else is installed on your laptop. Task 8 adds HBase, Zeppelin and the Spark Thrift
Server (profiles `hbase`, `zeppelin`, guide in `SETUP.md`).

## Prerequisites
- Docker Desktop with **at least 6 GB of memory** (8 GB for `core` + `yarn`). Where to set it:
  - Windows (WSL 2 backend, the default): Docker Desktop has no memory setting; WSL gets half of the laptop's RAM,
    so 16 GB is enough. With less, create `C:\Users\<you>\.wslconfig` with the two lines `[wsl2]` and
    `memory=6GB` (`memory=8GB` if you need the `yarn` profile), run `wsl --shutdown` in PowerShell and start
    Docker Desktop again.
  - macOS (and Windows with the Hyper-V backend): Docker Desktop → Settings → Resources → Memory.
- Git; on Windows also Git Bash (for `check.sh`). Clone the repo anywhere.
- About 10 GB of free disk for the images and volumes (20 GB once you generate the 10× dataset).

## Start, stop, reset
Run these in this `docker/` folder.

| What | Command |
|---|---|
| Start the core stack (HDFS, Hive, client) | `docker compose --profile core up -d` |
| Also start YARN (MapReduce, Spark on YARN, Hive on YARN: E1, E5) | `docker compose --profile core --profile yarn up -d` |
| Check that everything works | `./check.sh` (Git Bash on Windows) |
| Stop, keep all data | `docker compose --profile core --profile yarn down` |
| Stop and delete all data (HDFS, metastore) | `docker compose --profile core --profile yarn down -v` |
| Rebuild the images after a change in `stack/`, `hive/` or `requirements.txt` (run it after every rebase that brought new commits) | the command you first built with, e.g. `docker compose --profile core build --build-arg APACHE_MIRROR=https://dlcdn.apache.org` |

The first start builds the images `isit312/stack:1.0` (Hadoop, Spark, Python) and `isit312/hive:1.0` (about 15
minutes, downloads about 2 GB). The build takes
Hadoop and Spark from `archive.apache.org`; if that is slow, build with a faster mirror that still has these
versions: `docker compose --profile core build --build-arg APACHE_MIRROR=https://dlcdn.apache.org`.
Rebuild with the same mirror every time: a different `APACHE_MIRROR` value invalidates Docker's build cache, so
Hadoop and Spark are downloaded again (with the same value an unchanged rebuild takes seconds). To see which
mirror your image used: `docker history --no-trunc isit312/stack:1.0 | grep -o 'APACHE_MIRROR=[^ ]*' | head -1`.

`check.sh` waits until HiveServer2 answers (a minute or two after `up -d`), then prints:

```
OK hdfs
OK hive
OK spark
OK metastore
OK yarn          (only with --profile yarn)
OK hive-yarn     (only with --profile yarn)
```

A failed check prints `FAIL <name>: <first error line>` and the script exits with 1.

## Services and ports
| Service | Profile | What | Host port |
|---|---|---|---|
| `namenode` | core | HDFS NameNode | 9870 (web UI), 8020 |
| `datanode` | core | HDFS DataNode | 9864 |
| `metastore` | core | Hive metastore 3.1.3 (Derby in the volume `hive_metastore_db`) | 9083 |
| `hiveserver2` | core | HiveServer2 3.1.3 with the stack's Hadoop 3.3.6 client; MapReduce in local mode | 10000 (JDBC), 10002 (web UI) |
| `client` | core | Python 3.10, Spark 3.5.9, Hadoop client, the repo at `/repo` | 4040 (Spark UI) |
| `resourcemanager` | yarn | YARN ResourceManager | 8088 (web UI) |
| `nodemanager` | yarn | YARN NodeManager (2 GB for containers) | 8042 |
| `historyserver` | yarn | MapReduce job history | 19888 |

Data lives in the named volumes `hdfs_nn`, `hdfs_dn` and `hive_metastore_db`: `down` keeps it, `down -v` deletes it.

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

## Memory tips
- `core` needs about 4.5 GB, `yarn` about 3 GB more. Start `yarn` only when you need it, and stop it afterwards
  with `docker compose stop resourcemanager nodemanager historyserver`.
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
| Apple Silicon Mac | `apache/hive:3.1.3` exists only for amd64: enable "Use Rosetta for x86/amd64 emulation" in Docker Desktop; Hive is slower there |

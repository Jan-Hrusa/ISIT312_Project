# ISIT312 Docker Environment — Setup Guide

This guide explains how to install, configure and run the ISIT312 project environment on Windows, macOS and Linux.

The project uses Docker to run HDFS, Hive, Spark, YARN, HBase, Spark Thrift Server and Zeppelin.

All project code, tests and tools run inside the Docker `client` container. You do not need to install Hadoop, Spark, Hive or Python dependencies directly on your computer.

Commands, ports and the client-container workflow are in [README.md](README.md); this guide covers getting a
machine ready and which profiles your area needs.

---

# 1. System Requirements

## Hardware Requirements

| Resource | Minimum Recommendation |
|---|---|
| RAM | 16 GB recommended |
| Free disk space | 10 GB minimum (core); 25 GB with the `zeppelin` profile; 20 GB more for the 10× dataset |
| Processor | Modern 64-bit processor |
| Internet | Required for downloading Docker images and dependencies |

## Docker Memory Requirements

Different project profiles require different amounts of memory.

| Configuration | Approximate Memory |
|---|---:|
| Core (HDFS, Hive, Spark, client) | 4.5 GB |
| Core + HBase | 5.5 GB |
| Core + Zeppelin (Spark Thrift Server + Zeppelin) | 7 GB |
| Core + HBase + Zeppelin | 8 GB |
| Core + YARN | 7.5 GB |

Avoid running unnecessary profiles simultaneously, especially on computers with limited RAM.

## Profiles per Area

| Area | Member | Profiles | Notes |
|---|---|---|---|
| 1 | Jan (lead) | all | integration day, end-to-end run |
| 2 | Jayden | core | |
| 3 | Obaid | core; + yarn for E1 (Task 23.1) | ~20 GB free disk for the 10× dataset |
| 4 | Muhammad | core | ~20 GB free disk for the 10× dataset (E2) |
| 5 | Ryan | all | |
| 6 | Riya | core | |
| 7 | Mudabbir | core + zeppelin | "to fix" and overdue notebooks; ~25 GB free disk |
| 8 | Gokulsanjay | core; + yarn and zeppelin for E5 (Task 31.1) | ~20 GB free disk for the 10× dataset, plus ~15 GB for zeppelin |
| 9 | Maysoon | core + zeppelin | dashboard; ~25 GB free disk |
| 10 | Aryen | core + hbase + zeppelin | 8 GB of Docker memory and ~25 GB free disk, or GitHub Codespaces (section 12) |

## Software Requirements

- Docker Desktop (Windows/macOS) or Docker Engine (Linux).
- Git.
- Git Bash on Windows.
- A terminal application.
- Visual Studio Code or another text editor (recommended).

---

# 2. Windows Setup

## Step 1 — Install WSL 2

Open PowerShell as Administrator and run:

```powershell
wsl --install
```
Restart your computer if requested.

Check that WSL is installed:

```powershell
wsl --status
```
Ensure that WSL 2 is being used.

## Step 2 — Install Docker Desktop

1. Download Docker Desktop for Windows.
2. Install Docker Desktop.
3. During installation, use the WSL 2 backend.
4. Open Docker Desktop.
5. Navigate to Settings → General.
6. Ensure that the WSL 2 based engine is enabled.
7. Wait until Docker Desktop reports that the engine is running.

Official download: https://www.docker.com/products/docker-desktop/

## Step 3 — Install Git

Download and install Git for Windows.

Git Bash is recommended because the project's `check.sh` script uses Bash.

Official download: https://git-scm.com/downloads

## Step 4 — Configure WSL Memory

Docker Desktop uses WSL 2 for its Linux environment.

If Docker does not have enough available memory, configure WSL using a `.wslconfig` file.

Create the file:

```text
C:\Users\<your-username>\.wslconfig
```
For an 8 GB allocation, use:

```ini
\[wsl2]

memory=8GB
```
Save the file.

Open PowerShell and run:

```powershell
wsl --shutdown
```
Restart Docker Desktop.

Adjust the allocation according to your available laptop memory and the profiles you need to run.

## Step 5 — Verify Installation

Open Git Bash and run:

```bash
docker --version

docker compose version

git --version
```
All three commands should return version information.

---

# 3. macOS Setup

## Step 1 — Install Docker Desktop

Download Docker Desktop for macOS.

Choose the correct installer for your processor:

- Apple Silicon (M1, M2, M3 and newer).
- Intel processor.

Official download:

https://www.docker.com/products/docker-desktop/

Install and open Docker Desktop.

Wait until the Docker engine is running.

## Step 2 — Configure Docker Memory

1. Open Docker Desktop.
2. Navigate to Settings → Resources.
3. Configure sufficient memory for the profiles you intend to run.
4. Apply the changes and restart Docker Desktop if requested.

Recommended allocations:

| Configuration | Memory |
|---|---:|
| Core | 4.5 GB |
| Core + HBase | 5.5 GB |
| Core + Zeppelin (Spark Thrift Server + Zeppelin) | 7 GB |
| Core + HBase + Zeppelin | 8 GB |
| Core + YARN | 7.5 GB |

## Step 3 — Install Git

Install Git using the official instructions:

https://git-scm.com/downloads

Verify:

```bash
git --version
```
## Step 4 — Apple Silicon Compatibility

Some project images are built for the AMD64 architecture.

On Apple Silicon Macs:

1. Open Docker Desktop.
2. Navigate to Settings.
3. Locate the Virtual Machine or General settings for architecture emulation.
4. Enable Rosetta or AMD64/x86 emulation where available.
5. Restart Docker Desktop.

AMD64 emulation can reduce performance compared with native execution.

---

# 4. Linux Setup

## Step 1 — Install Docker Engine

Install Docker Engine and the Docker Compose plugin using the official instructions for your Linux distribution.

Documentation:

https://docs.docker.com/engine/install/

## Step 2 — Verify Docker

Run:

```bash
docker --version

docker compose version
```
Both commands should return version information.

## Step 3 — Configure Docker Permissions

If your Linux installation requires it, add your user to the Docker group:

```bash
sudo usermod -aG docker $USER
```
Log out and log back in for the group change to take effect.

Verify:

```bash
docker ps
```
If Docker requires elevated permissions on your installation, use `sudo` where appropriate.

## Step 4 — Install Git

Install Git using your distribution's package manager.

For Ubuntu/Debian:

```bash
sudo apt update

sudo apt install git
```
Verify:

```bash
git --version
```
---

# 5. Clone the Project

Clone the project repository:

```bash
git clone https://github.com/Jan-Hrusa/ISIT312_Project.git
```
Navigate into the repository:

```bash
cd ISIT312_Project
```
Navigate into the Docker directory:

```bash
cd docker
```
All Docker Compose commands in this guide should be executed from this directory.

## Your Branch

Work only on your own branch (your first name in lower case). Create it once, from `integration`:

```bash
git fetch origin
git switch -c <name> --no-track origin/integration
git push -u origin <name>
```

Without `--no-track` the branch would track `integration`, so `git status` and a bare `git push` mislead.
Before any work in a session, bring it up to date: `git fetch origin`, then `git rebase origin/integration`
(the full rule is in the repository's `AGENTS.md`, section 3).

## First Build

The first start builds the images (about 15 minutes; Hadoop, Spark and HBase are downloaded once). If
`archive.apache.org` is slow, build with a faster mirror, adding every profile you use:

```bash
docker compose --profile core build --build-arg APACHE_MIRROR=https://dlcdn.apache.org
```

**Always rebuild with the same mirror you first used** (after every rebase that brought new commits): a
different `APACHE_MIRROR` value invalidates Docker's build cache and downloads Hadoop and Spark again. Which
mirror your image used: `docker history --no-trunc isit312/stack:1.0 | grep -o 'APACHE_MIRROR=[^ ]*' | head -1`.

---

# 6. Starting the Project

The project uses Docker Compose profiles to control which services are started.

## Core Profile

Starts HDFS, Hive, Spark and the client environment.

```bash
docker compose --profile core up -d
```
## YARN Profile

Starts the core environment and YARN services.

```bash
docker compose --profile core --profile yarn up -d
```
## HBase Profile

Starts the core environment and HBase.

```bash
docker compose --profile core --profile hbase up -d
```
## Zeppelin and Spark Thrift Server

Starts the core environment, Spark Thrift Server and Zeppelin (enough for the dashboards).

```bash
docker compose --profile core --profile zeppelin up -d
```
For the search notebook (Area 10), add `--profile hbase`:

```bash
docker compose --profile core --profile hbase --profile zeppelin up -d
```
## Verify Running Containers

```bash
docker compose ps
```
## Run Automated Checks

```bash
./check.sh
```
On Windows, execute this command using Git Bash.

The script checks the available services and reports:

- `OK` when a check passes.
- `FAIL` when a check fails.
- `SKIP` when an optional service is not running.

---

# 7. Accessing the Services

When the relevant profiles are running, the following interfaces are available:

| Service | Address |
|---|---|
| HDFS NameNode UI | http://localhost:9870 |
| YARN ResourceManager UI | http://localhost:8088 |
| HBase UI | http://localhost:16010 |
| Spark Thrift Server | localhost:10001 |
| Spark UI | http://localhost:4041 |
| Zeppelin | http://localhost:8080 |
| HiveServer2 JDBC | localhost:10000 |

Some services are only accessible when their corresponding profiles are running.

---

# 8. Working Inside the Client Container

The client container contains the project's development tools and dependencies.

Open a shell:

```bash
docker compose exec client bash
```
Run unit tests:

```bash
docker compose exec client pytest -m "not integration"
```
Run lint checks:

```bash
docker compose exec client ruff check .

docker compose exec client ruff format --check .
```
Run a Python module:

```bash
docker compose exec client python -m generators.bank
```
List HDFS files:

```bash
docker compose exec client hdfs dfs -ls /lake
```
The repository is mounted inside the container at `/repo`.

Changes made on your computer are reflected inside the container.

---

# 9. Stopping the Environment

Stop the core and YARN profiles while keeping data:

```bash
docker compose --profile core --profile yarn down
```
Stop all profiles while keeping data:

```bash
docker compose --profile core --profile yarn --profile hbase --profile zeppelin down
```
To stop and delete Docker volumes and stored data:

```bash
docker compose --profile core --profile yarn --profile hbase --profile zeppelin down -v
```
**Warning:** The `down -v` command deletes persistent Docker volumes, including stored HDFS and metastore data. Only use it when a complete reset is intended.

---

# 10. Disk Space Management

The Docker environment downloads several large images.

Recommendations:

- Keep at least 10 GB of free disk space for the core images and volumes. The `zeppelin` profile adds about
  15 GB (the official Zeppelin image alone is about 14 GB on disk), and a build needs extra room for its cache
  while it runs.
- Allow approximately 20 GB when generating the 10× dataset.
- Ensure that the computer has sufficient free space before building images.
- Avoid deleting Docker volumes unless a complete reset is intended.

Check available container storage:

```bash
docker system df
```
Check current container memory usage:

```bash
docker stats
```
Avoid using destructive Docker cleanup commands unless you understand which images, caches and volumes will be removed.

## Windows: Reclaiming Space

Docker Desktop keeps all images and volumes in one disk file (`docker_data.vhdx`, under
`%LOCALAPPDATA%\Docker\wsl\` by default). It grows with every build and does **not** shrink when you delete
images. If your system drive gets full:

1. Remove old build cache: `docker builder prune` (images and volumes stay).
2. Quit Docker Desktop, then in an administrator PowerShell compact the file (Windows Home has no
   `Optimize-VHD`, so this uses diskpart; adjust the path if you moved the disk image):

```powershell
wsl --shutdown
$v = "$env:LOCALAPPDATA\Docker\wsl\disk\docker_data.vhdx"
"select vdisk file=`"$v`"`r`nattach vdisk readonly`r`ncompact vdisk`r`ndetach vdisk" | Out-File -Encoding ascii "$env:TEMP\compact.txt"
diskpart /s "$env:TEMP\compact.txt"
```

3. Start Docker Desktop again.

---

# 11. Troubleshooting

| Problem | Possible Solution |
|---|---|
| Docker daemon is not running | Open Docker Desktop and wait until the engine starts. |
| WSL 2 errors on Windows | Run `wsl --status` and verify the WSL installation. |
| Containers restart unexpectedly | Check available Docker memory and close unnecessary applications. |
| Port already allocated | Another application may be using the port. Stop that application or investigate the conflicting port. |
| HiveServer2 is not responding | Wait for startup and inspect `docker compose logs hiveserver2 --tail 50`. |
| HBase is unavailable | Check `docker compose --profile core --profile hbase logs hbase --tail 50`. |
| Spark Thrift Server is unavailable | Check `docker compose --profile core --profile zeppelin logs sparksql --tail 50`. |
| Zeppelin UI does not load | Check `docker compose --profile core --profile zeppelin logs zeppelin --tail 50`. |
| A rebuild downloads Hadoop and Spark again | You built with a different `APACHE_MIRROR` than the first time; see First Build. |
| Hive and Zeppelin are very slow on an Apple Silicon Mac | Their images are amd64-only and run under emulation; use Rosetta (faster than QEMU), start only the profiles you need, or use Codespaces. |
| `check.sh` reports bad interpreter | Check that the script uses LF rather than CRLF line endings. |
| Docker runs out of disk space | Free space on the host machine before rebuilding images; on Windows also see Windows: Reclaiming Space. |
| Apple Silicon compatibility issues | Enable AMD64 emulation/Rosetta in Docker Desktop where required. |
| A service cannot connect to another service | Verify that the required Compose profiles are running and inspect container logs. |

---

# 12. GitHub Codespaces Fallback

If a team member's computer cannot run the Docker environment because of hardware, memory or operating-system limitations, GitHub Codespaces may be considered as an alternative development environment.

General approach:

1. Open the project repository on GitHub and choose a 4-core (16 GB) machine type, which fits core plus one
   extra profile.
2. Check whether Codespaces is enabled for the repository.
3. Create a Codespace if access is available.
4. Verify that Docker and Docker Compose are available in the environment.
5. Run the same `docker compose` commands as on a laptop (the compose file is unchanged).
6. Run the automated checks.
7. Confirm that the required services can start successfully.

Codespaces availability, storage, memory and Docker-in-Docker support depend on the environment and account configuration. Confirm these requirements before relying on Codespaces for the full stack.

If the complete environment cannot run in Codespaces, coordinate with another team member who has a working local setup.

---

# 13. Team Setup and Testing Record

Each team member should record whether they successfully installed and tested the Docker environment.

Do not mark a setup as successful until the member has actually run the relevant services and checks.

| Team Member | Area | Operating System | RAM | Core | YARN | HBase | Zeppelin | Result / Notes |
|---|---|---|---|---|---|---|---|---|
| Jan | 1 | Windows 10 (desktop) | Docker VM 8 GB | Yes | Yes | Yes | Yes | 14 Nov, Task 8 review fixes on fresh volumes: check.sh all OK with core + zeppelin, core + hbase + zeppelin and core + yarn |
| Jayden | 2 | To be confirmed | – | Pending | – | – | – | Awaiting test |
| Obaid | 3 | To be confirmed | – | Pending | Pending | – | – | Awaiting test |
| Muhammad | 4 | To be confirmed | – | Pending | – | – | – | Awaiting test |
| Ryan | 5 | Windows 11 | – | Yes | – | Yes | Yes | Local setup tested (PR #29) |
| Riya | 6 | To be confirmed | – | Pending | – | – | – | Awaiting test |
| Mudabbir | 7 | To be confirmed | – | Pending | – | – | Pending | Awaiting test |
| Gokulsanjay | 8 | To be confirmed | – | Pending | Pending | – | Pending | Awaiting test |
| Maysoon | 9 | To be confirmed | – | Pending | – | – | Pending | Awaiting test |
| Aryen | 10 | To be confirmed | – | Pending | – | Pending | Pending | Awaiting test |

A dash means the profile isn't needed for that area (Profiles per Area). Send Ryan your OS, RAM and
`./check.sh` output with your area's profiles running.

Update this table only after receiving confirmation from each team member.

---

# 14. Support and Project References

For issues with the Docker environment:

1. Check this guide.
2. Check `README.md` in the Docker directory.
3. Inspect the relevant container logs.
4. Run `./check.sh` and share the failure output with the team.
5. Contact the project integration lead if the issue affects shared configuration or project contracts.

Always keep your branch synchronized with the project integration branch according to the team's Git workflow.

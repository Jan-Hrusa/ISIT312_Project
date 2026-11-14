\# ISIT312 Docker Environment — Setup Guide



This guide explains how to install, configure and run the ISIT312 project environment on Windows, macOS and Linux.



The project uses Docker to run HDFS, Hive, Spark, YARN, HBase, Spark Thrift Server and Zeppelin.



All project code, tests and tools run inside the Docker `client` container. You do not need to install Hadoop, Spark, Hive or Python dependencies directly on your computer.



\---



\# 1. System Requirements



\## Hardware Requirements



| Resource | Minimum Recommendation |

|---|---|

| RAM | 16 GB recommended |

| Free disk space | 10 GB minimum; 20 GB recommended |

| Processor | Modern 64-bit processor |

| Internet | Required for downloading Docker images and dependencies |



\## Docker Memory Requirements



Different project profiles require different amounts of memory.



| Configuration | Approximate Memory |

|---|---:|

| Core (HDFS, Hive, Spark, client) | 4.5 GB |

| Core + HBase | 5.5 GB |

| Core + HBase + Zeppelin | 8 GB |

| Core + YARN | 7.5 GB |



Avoid running unnecessary profiles simultaneously, especially on computers with limited RAM.



\## Software Requirements



\- Docker Desktop (Windows/macOS) or Docker Engine (Linux).

\- Git.

\- Git Bash on Windows.

\- A terminal application.

\- Visual Studio Code or another text editor (recommended).



\---



\# 2. Windows Setup



\## Step 1 — Install WSL 2



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



\## Step 2 — Install Docker Desktop



1\. Download Docker Desktop for Windows.

2\. Install Docker Desktop.

3\. During installation, use the WSL 2 backend.

4\. Open Docker Desktop.

5\. Navigate to Settings → General.

6\. Ensure that the WSL 2 based engine is enabled.

7\. Wait until Docker Desktop reports that the engine is running.



Official download: https://www.docker.com/products/docker-desktop/



\## Step 3 — Install Git



Download and install Git for Windows.



Git Bash is recommended because the project's `check.sh` script uses Bash.



Official download: https://git-scm.com/downloads



\## Step 4 — Configure WSL Memory



Docker Desktop uses WSL 2 for its Linux environment.



If Docker does not have enough available memory, configure WSL using a `.wslconfig` file.



Create the file:



```text

C:\\Users\\<your-username>\\.wslconfig

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



\## Step 5 — Verify Installation



Open Git Bash and run:



```bash

docker --version

docker compose version

git --version

```



All three commands should return version information.



\---



\# 3. macOS Setup



\## Step 1 — Install Docker Desktop



Download Docker Desktop for macOS.



Choose the correct installer for your processor:



\- Apple Silicon (M1, M2, M3 and newer).

\- Intel processor.



Official download:



https://www.docker.com/products/docker-desktop/



Install and open Docker Desktop.



Wait until the Docker engine is running.



\## Step 2 — Configure Docker Memory



1\. Open Docker Desktop.

2\. Navigate to Settings → Resources.

3\. Configure sufficient memory for the profiles you intend to run.

4\. Apply the changes and restart Docker Desktop if requested.



Recommended allocations:



| Configuration | Memory |

|---|---:|

| Core | 4.5 GB |

| Core + HBase | 5.5 GB |

| Core + HBase + Zeppelin | 8 GB |

| Core + YARN | 7.5 GB |



\## Step 3 — Install Git



Install Git using the official instructions:



https://git-scm.com/downloads



Verify:



```bash

git --version

```



\## Step 4 — Apple Silicon Compatibility



Some project images are built for the AMD64 architecture.



On Apple Silicon Macs:



1\. Open Docker Desktop.

2\. Navigate to Settings.

3\. Locate the Virtual Machine or General settings for architecture emulation.

4\. Enable Rosetta or AMD64/x86 emulation where available.

5\. Restart Docker Desktop.



AMD64 emulation can reduce performance compared with native execution.



\---



\# 4. Linux Setup



\## Step 1 — Install Docker Engine



Install Docker Engine and the Docker Compose plugin using the official instructions for your Linux distribution.



Documentation:



https://docs.docker.com/engine/install/



\## Step 2 — Verify Docker



Run:



```bash

docker --version

docker compose version

```



Both commands should return version information.



\## Step 3 — Configure Docker Permissions



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



\## Step 4 — Install Git



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



\---



\# 5. Clone the Project



Clone the project repository:



```bash

git clone <PROJECT\_REPOSITORY\_URL>

```



Navigate into the repository:



```bash

cd ISIT312\_Project

```



Navigate into the Docker directory:



```bash

cd docker

```



All Docker Compose commands in this guide should be executed from this directory.



\---



\# 6. Starting the Project



The project uses Docker Compose profiles to control which services are started.



\## Core Profile



Starts HDFS, Hive, Spark and the client environment.



```bash

docker compose --profile core up -d

```



\## YARN Profile



Starts the core environment and YARN services.



```bash

docker compose --profile core --profile yarn up -d

```



\## HBase Profile



Starts the core environment and HBase.



```bash

docker compose --profile core --profile hbase up -d

```



\## Zeppelin and Spark Thrift Server



Starts the core environment, HBase, Spark Thrift Server and Zeppelin.



```bash

docker compose --profile core --profile hbase --profile zeppelin up -d

```



\## Verify Running Containers



```bash

docker compose ps

```



\## Run Automated Checks



```bash

./check.sh

```



On Windows, execute this command using Git Bash.



The script checks the available services and reports:



\- `OK` when a check passes.

\- `FAIL` when a check fails.

\- `SKIP` when an optional service is not running.



\---



\# 7. Accessing the Services



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



\---



\# 8. Working Inside the Client Container



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



\---



\# 9. Stopping the Environment



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



\*\*Warning:\*\* The `down -v` command deletes persistent Docker volumes, including stored HDFS and metastore data. Only use it when a complete reset is intended.



\---



\# 10. Disk Space Management



The Docker environment downloads several large images.



Recommendations:



\- Keep at least 10 GB of free disk space for the environment.

\- Allow approximately 20 GB when generating the 10× dataset.

\- Ensure that the computer has sufficient free space before building images.

\- Avoid deleting Docker volumes unless a complete reset is intended.



Check available container storage:



```bash

docker system df

```



Check current container memory usage:



```bash

docker stats

```



Avoid using destructive Docker cleanup commands unless you understand which images, caches and volumes will be removed.



\---



\# 11. Troubleshooting



| Problem | Possible Solution |

|---|---|

| Docker daemon is not running | Open Docker Desktop and wait until the engine starts. |

| WSL 2 errors on Windows | Run `wsl --status` and verify the WSL installation. |

| Containers restart unexpectedly | Check available Docker memory and close unnecessary applications. |

| Port already allocated | Another application may be using the port. Stop that application or investigate the conflicting port. |

| HiveServer2 is not responding | Wait for startup and inspect `docker compose logs hiveserver2 --tail 50`. |

| HBase is unavailable | Check `docker compose --profile core --profile hbase logs hbase --tail 50`. |

| Spark Thrift Server is unavailable | Check `docker compose --profile core --profile hbase --profile zeppelin logs sparksql --tail 50`. |

| Zeppelin UI does not load | Check `docker compose --profile core --profile hbase --profile zeppelin logs zeppelin --tail 50`. |

| `check.sh` reports bad interpreter | Check that the script uses LF rather than CRLF line endings. |

| Docker runs out of disk space | Free space on the host machine before rebuilding images. |

| Apple Silicon compatibility issues | Enable AMD64 emulation/Rosetta in Docker Desktop where required. |

| A service cannot connect to another service | Verify that the required Compose profiles are running and inspect container logs. |



\---



\# 12. GitHub Codespaces Fallback



If a team member's computer cannot run the Docker environment because of hardware, memory or operating-system limitations, GitHub Codespaces may be considered as an alternative development environment.



General approach:



1\. Open the project repository on GitHub.

2\. Check whether Codespaces is enabled for the repository.

3\. Create a Codespace if access is available.

4\. Verify that Docker and Docker Compose are available in the environment.

5\. Follow the project Docker setup instructions.

6\. Run the automated checks.

7\. Confirm that the required services can start successfully.



Codespaces availability, storage, memory and Docker-in-Docker support depend on the environment and account configuration. Confirm these requirements before relying on Codespaces for the full stack.



If the complete environment cannot run in Codespaces, coordinate with another team member who has a working local setup.



\---



\# 13. Team Setup and Testing Record



Each team member should record whether they successfully installed and tested the Docker environment.



Do not mark a setup as successful until the member has actually run the relevant services and checks.



| Team Member | Operating System | Core Tested | HBase Tested | Zeppelin Tested | Result / Notes |

|---|---|---|---|---|---|

| Ryan | Windows 11 | Yes | Yes | Yes | Local setup tested |

| Aryen | To be confirmed | Pending | Pending | Pending | Awaiting test |

| Mudabbir | To be confirmed | Pending | Pending | Pending | Awaiting test |

| Maysoon | To be confirmed | Pending | Pending | Pending | Awaiting test |

| Gokulsanjay | To be confirmed | Pending | Pending | Pending | Awaiting test |



Update this table only after receiving confirmation from each team member.



\---



\# 14. Support and Project References



For issues with the Docker environment:



1\. Check this guide.

2\. Check `README.md` in the Docker directory.

3\. Inspect the relevant container logs.

4\. Run `./check.sh` and share the failure output with the team.

5\. Contact the project integration lead if the issue affects shared configuration or project contracts.



Always keep your branch synchronized with the project integration branch according to the team's Git workflow.

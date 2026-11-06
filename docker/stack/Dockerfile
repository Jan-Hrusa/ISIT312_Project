# isit312/stack:1.0 - Hadoop 3.3.6, Spark 3.5.9 and the project's Python packages on Java 11 (Task 3).
# One image for namenode, datanode, client and the YARN services; each picks its role through `command:`.
# Build context is the repo root (see docker-compose.yml).

ARG HIVE_IMAGE=apache/hive:3.1.3

# Hive 3.1.3 metastore client jars for Spark (spark.sql.hive.metastore.jars=path). Copied flat because the
# `*` in spark.sql.hive.metastore.jars.path does not recurse. The Hive image exists for amd64 only.
FROM --platform=linux/amd64 ${HIVE_IMAGE} AS hivejars
USER root
RUN mkdir /jars \
    && cp /opt/hive/lib/*.jar /jars/ \
    && find /opt/hadoop/share/hadoop -name '*.jar' -not -path '*/sources/*' -not -name '*-tests.jar' \
         -exec cp -n {} /jars/ \;

FROM eclipse-temurin:11-jdk-jammy

ARG TARGETARCH
ARG HADOOP_VERSION=3.3.6
ARG SPARK_VERSION=3.5.9
ARG APACHE_MIRROR=https://archive.apache.org/dist

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip curl procps openjdk-8-jre-headless \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s "/usr/lib/jvm/java-8-openjdk-$(dpkg --print-architecture)/jre" /opt/java8
# Java 11 runs everything; /opt/java8 is only for the YARN tasks of Hive jobs (Hive 3.1 supports Java 8 only, see
# docker/conf/hive-site.xml).

RUN set -eux; \
    if [ "${TARGETARCH:-amd64}" = "arm64" ]; then suffix="-aarch64"; else suffix=""; fi; \
    curl -fsSL "${APACHE_MIRROR}/hadoop/common/hadoop-${HADOOP_VERSION}/hadoop-${HADOOP_VERSION}${suffix}.tar.gz" \
      | tar -xz -C /opt; \
    mv "/opt/hadoop-${HADOOP_VERSION}" /opt/hadoop; \
    rm -rf /opt/hadoop/share/doc

RUN set -eux; \
    curl -fsSL "${APACHE_MIRROR}/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz" \
      | tar -xz -C /opt; \
    mv "/opt/spark-${SPARK_VERSION}-bin-hadoop3" /opt/spark

COPY --from=hivejars /jars /opt/hive-metastore-jars

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# All daemons and the client run as `hadoop` (uid 1000), the HDFS superuser. /data holds the HDFS volumes.
RUN useradd --create-home --uid 1000 --shell /bin/bash hadoop \
    && mkdir -p /data/nn /data/dn /opt/conf \
    && chown -R hadoop:hadoop /data /opt/hadoop /opt/spark \
    && ln -s /usr/bin/python3 /usr/local/bin/python

ENV HADOOP_HOME=/opt/hadoop \
    HADOOP_CONF_DIR=/opt/conf \
    SPARK_HOME=/opt/spark \
    SPARK_CONF_DIR=/opt/conf \
    HADOOP_USER_NAME=hadoop \
    PYSPARK_PYTHON=python3 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/hadoop/bin:/opt/hadoop/sbin:/opt/spark/bin:${PATH}

USER hadoop
WORKDIR /repo

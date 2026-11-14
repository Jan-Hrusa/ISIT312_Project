FROM apache/zeppelin:0.11.2

USER root

# Install Python libraries required for HBase and data analysis
RUN python3 -m pip install --no-cache-dir happybase pandas

# Download the standalone Hive JDBC driver
RUN mkdir -p /opt/hive/jdbc \
    && curl -fL https://repo.maven.apache.org/maven2/org/apache/hive/hive-jdbc/3.1.3/hive-jdbc-3.1.3-standalone.jar \
    -o /opt/hive/jdbc/hive-jdbc-3.1.3-standalone.jar

# Make the driver available to Zeppelin's JDBC interpreter
RUN cp /opt/hive/jdbc/hive-jdbc-3.1.3-standalone.jar \
    /opt/zeppelin/interpreter/jdbc/

# Restore the original Zeppelin runtime user
COPY --chown=1000:0 interpreter.json /opt/zeppelin/conf/interpreter.json
USER 1000:0
# isit312/hive:1.0 - HiveServer2: apache/hive:3.1.3 with the stack's Hadoop 3.3.6 client instead of its 3.1.0.
# With 3.1.0, Hive's jobs on YARN fail in the 3.3.6 NodeManager: the old client writes its RPC engine
# (ProtobufRpcEngine) into the job configuration and the application master dies with a protobuf
# ClassCastException. Built by docker compose; `stack` is the image of the namenode service (isit312/stack:1.0).
FROM apache/hive:3.1.3
USER root
RUN rm -rf /opt/hadoop
COPY --from=stack /opt/hadoop /opt/hadoop
USER hive

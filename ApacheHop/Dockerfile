FROM apache/hop:2.16.0

USER root

RUN mkdir -p /project/data \
    /project/pipelines \
    /project/workflows

RUN chown -R hop:hop /project

USER hop

WORKDIR /project
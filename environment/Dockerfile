# hash:sha256:b9d0616de1e4a61eab54d3fc8aeb362ebde0db4dfe49f97110cac02cb2726243
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-askpass /

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        vim=2:8.2.3995-1ubuntu2.24 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -U --no-cache-dir \
    aind-data-schema==1.4.0 \
    aind-data-schema-models==0.7.5 \
    aind-pophys-converter==0.0.1 \
    aind-qcportal-schema==0.4.0 \
    pydantic-settings==2.8.1 \
    pytz==2025.2 \
    tifffile==2024.2.12

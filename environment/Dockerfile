# hash:sha256:63f818bd7cde57de17416812706a2d3940f7489e969f8825aa26e4b9beacbcc7
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/code-server-python-extensions-pack:code-server4.108.2python3.12.4aind-metadata-mcp0.5.2withDOTFILES_REPOsupport

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

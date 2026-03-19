# hash:sha256:5ba56bdc47e3605e96b99ae09fbbd7347c04bb06ed4514ca4d9ab856d9735b01
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/code-server-python-extensions-pack:code-server4.108.2python3.12.4aind-metadata-mcp0.5.2withDOTFILES_REPOsupport

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-ask-pass /

RUN pip install -U --no-cache-dir \
    aind-data-schema==2.6.0 \
    aind-data-schema-models==5.4.1 \
    aind-log-utils==0.2.6 \
    aind-pophys-converter==0.0.1 \
    aind-qcportal-schema==0.6.4 \
    pydantic-settings==2.8.1 \
    pytz==2025.2 \
    tifffile==2024.2.12

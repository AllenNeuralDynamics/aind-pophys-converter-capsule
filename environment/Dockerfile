# hash:sha256:c2bd857ffbdb9ff01a61b7728b348e5f9e2b27aad5e31a9b24c2cea2e6f65fdb
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive

ARG GIT_ASKPASS
ARG GIT_ACCESS_TOKEN
COPY git-askpass /

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        vim=2:8.2.3995-1ubuntu2.24 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -U --no-cache-dir \
    pydantic-settings==2.8.1 \
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter.git@initial-build#egg=aind-pophys-converter

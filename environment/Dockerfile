# hash:sha256:874bdf4be7a7733b3a082922c924f61761c713f47a3d6dab7102cd59a43cde63
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive

ARG GIT_ASKPASS
ARG GIT_ACCESS_TOKEN
COPY git-askpass /

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        vim=2:8.2.3995-1ubuntu2.23 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -U --no-cache-dir \
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter.git@initial-build#egg=aind-pophys-converter

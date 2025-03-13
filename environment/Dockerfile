# hash:sha256:2de79c0c13814bc2f30b9c44b574f2690f50bbd8c9d8c5debaf7c1db3514dfcb
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
    pydantic-settings==2.8.1 \
    scanimage-tiff-reader==1.4.1.4 \
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter.git@initial-build#egg=aind-pophys-converter

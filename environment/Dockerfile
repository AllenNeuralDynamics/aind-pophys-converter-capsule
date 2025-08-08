# hash:sha256:46e4dc71a0ab27dedfaeed4eeeb1f43c645736c5f6d81ee1a8ba9df0aa8b2830
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG AWS_ACCESS_KEY_ID
ARG AWS_DEFAULT_REGION
ARG AWS_SECRET_ACCESS_KEY

ARG GIT_ASKPASS
ARG GIT_ACCESS_TOKEN
COPY git-askpass /

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        vim=2:8.2.3995-1ubuntu2.24 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -U --no-cache-dir \
    pydantic-settings==2.8.1 \
    requests==2.32.4 \
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter.git@initial-build#egg=aind-pophys-converter

# hash:sha256:c7cbf73f738724bdd4d92afc8a044d349f306104273fedc4bfd447109b84c06c
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
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter@84f6a09cd1f37eff79109f9bb07a553150404db2#egg=aind-pophys-converter
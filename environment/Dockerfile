# hash:sha256:c1daad6a163906e672ca980304d5f7fb3520f8bc80bbf1b36b658a47de27247c
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-askpass /

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        vim=2:8.2.3995-1ubuntu2.24 \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=secret,id=git-access-token \
    GIT_ACCESS_TOKEN="$(cat /run/secrets/git-access-token)" \
    pip install -U --no-cache-dir \
    aind-data-schema==1.4.0 \
    aind-data-schema-models==0.7.5 \
    pydantic-settings==2.8.1 \
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter@84f6a09cd1f37eff79109f9bb07a553150404db2#egg=aind-pophys-converter

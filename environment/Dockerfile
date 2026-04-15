# hash:sha256:ca4bfeb0e3e665d9f8ab0b1307e61c47d98b72531dc3b76e21d9447049c560c6
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-ask-pass /

RUN --mount=type=secret,id=git-access-token \
    GIT_ACCESS_TOKEN="$(cat /run/secrets/git-access-token)" \
    pip install -U --no-cache-dir \
    aind-data-schema \
    aind-data-schema-models==5.4.1 \
    aind-log-utils==0.2.6 \
    aind-qcportal-schema==0.6.4 \
    pydantic-settings==2.8.1 \
    pytz==2025.2 \
    tifffile==2024.2.12 \
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter.git@38eb0ae2133b6e427588d3a103498aa2cba3082e#egg=aind-pophys-converter

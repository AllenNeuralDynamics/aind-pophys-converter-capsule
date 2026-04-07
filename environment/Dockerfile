# hash:sha256:0becc1d0e8611c8566ca2b0c5d371258ac1b11c7c7eb660acfd63968a594142b
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-ask-pass /

RUN --mount=type=secret,id=git-access-token \
    GIT_ACCESS_TOKEN="$(cat /run/secrets/git-access-token)" \
    pip install -U --no-cache-dir \
    aind-data-schema==1.4.0 \
    aind-data-schema-models==0.7.5 \
    aind-qcportal-schema==0.4.0 \
    pydantic-settings==2.8.1 \
    pytz==2025.2 \
    tifffile==2024.2.12 \
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter.git@776930e#egg=aind-pophys-converter

# hash:sha256:42ff4c3545bd6db1e0355082f6e571eb9e85234076901650cee86beb3e755434
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-ask-pass /

RUN --mount=type=secret,id=git-access-token \
    GIT_ACCESS_TOKEN="$(cat /run/secrets/git-access-token)" \
    pip3 install -U --no-cache-dir \
    aind-data-schema==1.4.0 \
    aind-data-schema-models==0.7.5 \
    aind-qcportal-schema==0.4.0 \
    pydantic-settings==2.8.1 \
    pytz==2025.2 \
    tifffile==2024.2.12 \
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter.git@v0.1.1#egg=aind-pophys-converter

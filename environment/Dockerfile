# hash:sha256:c3992a0dcf0154c55655eff4c175b91bf3f40fb40bdfb1716cc91edf12cb7baf
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive

ARG GIT_ASKPASS
ARG GIT_ACCESS_TOKEN
COPY git-askpass /

RUN pip install -U --no-cache-dir \
    pydantic-settings==2.8.1 \
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter.git@initial-build#egg=aind-pophys-converter

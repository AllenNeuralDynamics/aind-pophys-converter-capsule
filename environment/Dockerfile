# hash:sha256:6364bd98ecf4b09a8c87dfddf34cb4f3aad9e5c6528180125934a539cd50abe5
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:24.5.0-0-python3.12.4-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-ask-pass /

RUN --mount=type=secret,id=git-access-token \
    GIT_ACCESS_TOKEN="$(cat /run/secrets/git-access-token)" \
    pip3 install -U --no-cache-dir \
    -e git+https://github.com/AllenNeuralDynamics/aind-pophys-converter.git@23067b5#egg=aind-pophys-converter

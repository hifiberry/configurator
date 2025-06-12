FROM debian:bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV BUILD_DIR=/build
ENV OUT_DIR=/out

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3 \
    python3-setuptools \
    python3-pip \
    python3-all \
    python3-stdeb \
    fakeroot \
    debhelper \
    dh-python \
    gnupg \
    lsb-release \
    curl \
    dpkg-dev \
    sudo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /tmp/build-dir && chmod 777 /tmp/build-dir

# Create required directories with appropriate permissions
RUN mkdir -p ${BUILD_DIR} ${OUT_DIR} && \
    # Make sure these directories are world-writable
    chmod 777 ${BUILD_DIR} ${OUT_DIR} && \
    # Also make the home directory writable for non-root users
    mkdir -p /tmp/home && chmod 777 /tmp/home

# Set environment variables for non-root users
ENV HOME=/tmp/home
ENV XDG_RUNTIME_DIR=/tmp/home

WORKDIR ${BUILD_DIR}

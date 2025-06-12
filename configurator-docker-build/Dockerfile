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
    gosu \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create required directories
RUN mkdir -p ${BUILD_DIR} ${OUT_DIR}

WORKDIR ${BUILD_DIR}

# Add entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Use our entrypoint script
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

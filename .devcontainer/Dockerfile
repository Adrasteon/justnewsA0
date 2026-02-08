FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install basic dev tools and Python
RUN apt-get update && apt-get install -y \
    curl git python3 python3-pip python3-venv python3-distutils \
    build-essential libmariadb-dev gpg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install `uv` tool (from PyPI) used to sync/build the dependency venv
RUN pip3 install --no-cache-dir uv

# Create app working dir
WORKDIR /app

# Add helper scripts (entrypoint copies are done during build)
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY scripts/create_deps_venv.sh /usr/local/bin/create_deps_venv.sh
COPY scripts/post-create.sh /usr/local/bin/post-create.sh
COPY scripts/run-publisher.sh /usr/local/bin/run-publisher.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/create_deps_venv.sh /usr/local/bin/post-create.sh /usr/local/bin/run-publisher.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["sleep", "infinity"]
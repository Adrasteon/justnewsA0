FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install basic dev tools, Python, and Redis
RUN apt-get update && apt-get install -y \
    curl git python3 python3-pip python3-venv python3-distutils \
    build-essential libmariadb-dev gpg ca-certificates \
    redis-server \
    libgbm-dev libasound2 libnss3 libxss1 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @playwright/mcp \
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
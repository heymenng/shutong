FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# 安装基础依赖
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    cmake \
    build-essential \
    libssl-dev \
    libyaml-cpp-dev \
    libeigen3-dev \
    libboost-all-dev \
    libspdlog-dev \
    libfmt-dev \
    libncurses5-dev \
    pkg-config \
    vim \
    net-tools \
    iputils-ping \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 编译安装 CycloneDDS 0.10.x
WORKDIR /opt
RUN git clone https://github.com/eclipse-cyclonedds/cyclonedds -b releases/0.10.x && \
    cd cyclonedds && mkdir build install && cd build && \
    cmake .. -DCMAKE_INSTALL_PREFIX=/opt/cyclonedds/install && \
    cmake --build . --target install -j$(nproc)

ENV CYCLONEDDS_HOME=/opt/cyclonedds/install

# 安装 unitree_sdk2_python
WORKDIR /opt
RUN git clone https://github.com/unitreerobotics/unitree_sdk2_python.git && \
    cd unitree_sdk2_python && \
    pip3 install -e .

# 安装书童桥接服务依赖
RUN pip3 install fastapi uvicorn websockets numpy opencv-python

# 暴露桥接服务端口
EXPOSE 8080

WORKDIR /opt/unitree_bridge
CMD ["python3", "bridge_server.py"]

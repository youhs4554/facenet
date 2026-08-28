FROM nvidia/cuda:12.8.1-devel-ubuntu22.04@sha256:6617a625f4090c76c545a0e7d63f2e441718ef9af7f4efe7dd1242a29e289fd7

ARG DEBIAN_FRONTEND=noninteractive
ARG A2F_SDK_COMMIT=1ca0f02535ed774f5dbcd724a31cd486368dc783
ARG TRT_OSS_COMMIT=94e2b9ef6d2cce74c76cdad499cca36cc4949197
ARG TRT_VERSION=10.13.3.9

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git git-lfs g++ make ninja-build cmake python3 python3-pip zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --no-deps \
      tensorrt-cu12-libs==10.13.3.9 \
      tensorrt-cu12-bindings==10.13.3.9 \
      tensorrt-cu12==10.13.3.9 \
      numpy==1.23.5

RUN git init /opt/tensorrt-oss \
    && git -C /opt/tensorrt-oss remote add origin https://github.com/NVIDIA/TensorRT.git \
    && git -C /opt/tensorrt-oss fetch --depth 1 origin ${TRT_OSS_COMMIT} \
    && git -C /opt/tensorrt-oss checkout --detach FETCH_HEAD \
    && test "$(git -C /opt/tensorrt-oss rev-parse HEAD)" = "${TRT_OSS_COMMIT}"

RUN TRT_LIB_DIR="$(python3 -c 'import pathlib,tensorrt_libs; print(pathlib.Path(tensorrt_libs.__file__).parent)')" \
    && mkdir -p /opt/tensorrt/include /opt/tensorrt/lib \
    && cp -a /opt/tensorrt-oss/include/. /opt/tensorrt/include/ \
    && ln -s "${TRT_LIB_DIR}/libnvinfer.so.10" /opt/tensorrt/lib/libnvinfer.so \
    && ln -s "${TRT_LIB_DIR}/libnvinfer_plugin.so.10" /opt/tensorrt/lib/libnvinfer_plugin.so \
    && ln -s "${TRT_LIB_DIR}/libnvonnxparser.so.10" /opt/tensorrt/lib/libnvonnxparser.so \
    && ln -s "${TRT_LIB_DIR}/libnvinfer_builder_resource.so.10.13.3" /opt/tensorrt/lib/libnvinfer_builder_resource.so.10.13.3

RUN git init /opt/a2f-sdk \
    && git -C /opt/a2f-sdk remote add origin https://github.com/NVIDIA/Audio2Face-3D-SDK.git \
    && git -C /opt/a2f-sdk fetch --depth 1 origin ${A2F_SDK_COMMIT} \
    && git -C /opt/a2f-sdk checkout --detach FETCH_HEAD \
    && git -C /opt/a2f-sdk lfs pull \
    && test "$(git -C /opt/a2f-sdk rev-parse HEAD)" = "${A2F_SDK_COMMIT}"

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV TENSORRT_ROOT_DIR=/opt/tensorrt
ENV LD_LIBRARY_PATH=/opt/tensorrt/lib:/usr/local/lib/python3.10/dist-packages/tensorrt_libs:/usr/local/cuda/lib64:/opt/a2f-sdk/_build/release/audio2x-sdk/lib

RUN cd /opt/a2f-sdk && ./fetch_deps.sh release

RUN cd /opt/a2f-sdk \
    && _deps/build-deps/cmake/bin/cmake -S . -B _build/release -G Ninja \
         -DCMAKE_BUILD_TYPE=Release \
         -DCMAKE_CUDA_ARCHITECTURES=86 \
         -DTENSORRT_ROOT_DIR=/opt/tensorrt \
         -DZLIB_ROOT=/opt/a2f-sdk/_deps/target-deps/zlib/release \
    && _deps/build-deps/cmake/bin/cmake --build _build/release --target audio2x --parallel 6

COPY geometry_exporter.cpp /opt/sidecar/geometry_exporter.cpp
RUN mkdir -p /opt/a2f/bin \
    && g++ -std=c++17 -O2 -D_GLIBCXX_USE_CXX11_ABI=0 \
       -I/opt/a2f-sdk/audio2face-sdk/include \
       -I/opt/a2f-sdk/audio2x-common/include \
       -I/usr/local/cuda/include \
       /opt/sidecar/geometry_exporter.cpp \
       -L/opt/a2f-sdk/_build/release/audio2x-sdk/lib -laudio2x \
       -L/usr/local/cuda/lib64 -lcudart \
       -Wl,-rpath,/opt/a2f-sdk/_build/release/audio2x-sdk/lib \
       -Wl,-rpath,/opt/tensorrt/lib \
       -o /opt/a2f/bin/a2f-geometry-exporter

COPY build_engine.py verify_outputs.py entrypoint.sh /opt/sidecar/
RUN chmod 0555 /opt/sidecar/entrypoint.sh /opt/sidecar/build_engine.py /opt/sidecar/verify_outputs.py \
    && /opt/a2f/bin/a2f-geometry-exporter --help

ENTRYPOINT ["/opt/sidecar/entrypoint.sh"]
CMD ["inspect"]

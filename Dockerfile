FROM debian:latest

ENV NGHTTP2_VERSION v1.17.0

RUN apt-get update && \
    apt-get install -y g++ make binutils autoconf automake autotools-dev libtool pkg-config \
    zlib1g-dev libcunit1-dev libssl-dev libxml2-dev libev-dev libevent-dev libjansson-dev \
    libjemalloc-dev git-core ca-certificates libyaml-dev python-dev python-pip && \
    cd /tmp && \
    git clone -b ${NGHTTP2_VERSION} --depth 1 https://github.com/nghttp2/nghttp2.git && \
    cd nghttp2 && \
    autoreconf -i && \
    automake && \
    autoconf && \
    ./configure && \
    make && \
    make install && \
    cd .. && \
    rm -rf nghttp2 && \
    apt-get remove -y make autoconf automake autotools-dev git-core && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/apt/lists/*

WORKDIR /app

COPY requirements.txt start nghttpx.conf /app/
RUN chmod 755 start && \
    pip install setuptools --upgrade && \
    pip install -r requirements.txt

COPY ingress-runner.py private.pem nginx_cert_chain.crt /app/

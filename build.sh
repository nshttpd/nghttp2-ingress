#!/bin/bash
set -ex

DIR=`pwd`
NAME=`basename ${DIR}`
VERSION='v1.17.0-2'

docker build -t ${NAME}:${VERSION} .
docker push ${NAME}:${VERSION}

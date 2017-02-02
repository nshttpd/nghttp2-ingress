# kubernetes nghttp2 ingress

Kubernetes Ingress using [nghttp2](https://nghttp2.org/)

Current Assumptions with this release :

* if you need SSL certificates they'll be in the same directory and named as per the Dockerfile
* The named port in the Service will be "http2" or "grpc" if HTTP2 is required on the backend.

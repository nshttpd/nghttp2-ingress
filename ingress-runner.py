#!/usr/bin/env python

import sys
import subprocess
import BaseHTTPServer
import pykube
import os
import signal
import time
from apscheduler.schedulers.background import BackgroundScheduler

PROXY = '/usr/local/bin/nghttpx'
CONFIG_FILE = '/app/nghttpx.conf'
PID_FILE = '/app/nghttpx.pid'

ingress_cache = {}

class DebugHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    # clip all /healthz request logging
    def log_message(self, format, *args):
        if self.path != '/healthz':
            print "%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format%args)

    def do_GET(self):
        if self.path == '/healthz':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write("OK")
            return
        if self.path == '/config':
            f = open(CONFIG_FILE, 'r')
            conf = f.read()
            f.close()
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            for line in conf.split('\n'):
                self.wfile.write(line + '\r\n')
            return
        self.send_error(404, 'Not Found')
        return


def get_ingresses():
    api = pykube.HTTPClient(pykube.KubeConfig.from_service_account())
    selector = os.environ.get('LABEL_SELECTOR')
    ingresses = []
    ingress_query = pykube.Ingress.objects(api)
    # we want all of them right now, this may change in the future
    ingress_query.namespace = None
    if selector is not None:
        select_parts = selector.split('=')
        ingress_query.selector = {'%s__eq' % select_parts[0]: select_parts[1]}
    for i in ingress_query:
        ingresses.append(i)
    return ingresses


def get_service(namespace, svc_name):
    api = pykube.HTTPClient(pykube.KubeConfig.from_service_account())
    service_query = pykube.Service.objects(api).filter(namespace=namespace)
    service = service_query.get_by_name(name=svc_name)
    return service


def validate_ingresses(ingresses):
    global ingress_cache
    rebuild = False
    # got a new one or removed one .. rebuild
    if len(ingress_cache) != len(ingresses):
        rebuild = True
    for i in ingresses:
        cache_key = '%s:%s' % (i.name, i.namespace)
        if cache_key not in ingress_cache:
            rebuild = True
            ingress_cache[cache_key] = i
        else:
            if ingress_cache[cache_key].obj['metadata']['resourceVersion'] != i.obj['metadata']['resourceVersion']:
                rebuild = True
                ingress_cache[cache_key] = i

    return rebuild


def build_config_file():
    ingresses = get_ingresses()
    rebuild = validate_ingresses(ingresses)
    if rebuild:
        print 'building config file'
        f = open(CONFIG_FILE, 'w')
        f.write('frontend=*,8080;no-tls\n')
        f.write('frontend=*,8443\n')
        # catch-all b/c you have to have one
        f.write('backend=nghttp2.org,80\n')
        # number of worker threads
        f.write('workers=%s\n' % os.environ.get('WORKERS', failobj='1'))
        for i in ingresses:
            print 'rebuilding name: %s - namespace: %s' % (i.name, i.namespace)
            for rule in i.obj['spec']['rules']:
                for path in rule['http']['paths']:
                    service = get_service(i.obj['metadata']['namespace'], path['backend']['serviceName'])
                    if service is not None:
                        for port in service.obj['spec']['ports']:
                            if port['name'] == path['backend']['servicePort']:
                                # clusterId,port;hostpath
                                proto = 'h2' if (port['name'] == 'http2' or 'grpc' in port['name']) else 'http/1.1'
                                f.write('backend=%s,%d;%s%s;proto=%s\n' % (service.obj['spec']['clusterIP'], port['port'], rule['host'], path['path'], proto))
        f.close()
        print 'done building config file'
    return rebuild


def is_alive():
    alive = True
    f = open(PID_FILE, 'r')
    pid = int(f.readline().rstrip())
    f.close()
    try:
        os.kill(pid, 0)
    except OSError:
        alive = False
    return alive


def hotswap_proxy():
    f = open(PID_FILE, 'r')
    pid = int(f.readline().rstrip())
    f.close()
    try:
        os.kill(pid, signal.SIGUSR2)
        time.sleep(5)
        os.kill(pid, signal.SIGQUIT)
    except OSError:
        print 'error trying to hotswap proxy'
    return


def reload_config():
    restart = build_config_file()
    if restart:
        print 'reloading config and hotswapping proxy'
        hotswap_proxy()
    return


def main(argv=None):
    if argv is None:
        argv = sys.argv

    build_config_file()

    proxy_args = [PROXY, '--conf=/app/nghttpx.conf', '--pid-file=%s' % PID_FILE, '--accesslog-file=/dev/stdout', '--add-x-forwarded-for', '--no-location-rewrite', '--daemon', '/app/private.pem', '/app/nginx_cert_chain.crt']
    subprocess.Popen(proxy_args)

    scheduler = BackgroundScheduler()
    scheduler.add_job(reload_config, 'interval', seconds=60)
    scheduler.start()

    server_addr = ('', 9090)

    server = BaseHTTPServer.HTTPServer(server_addr, DebugHandler)

    # give proxy time to start and write pid file before we start to
    # check for it. otherwise we were getting IOError
    time.sleep(2)

    while(is_alive()):
        server.handle_request()


if __name__ == '__main__':
    sys.exit(main())

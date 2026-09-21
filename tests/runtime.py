#!/usr/bin/env python3
"""Native disposable HTTPS runtime qualification. No credentials in artifacts."""
import base64
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import platform
import secrets
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

import requests

image, arch, output = sys.argv[1:]
assert platform.machine() == {'amd64': 'x86_64', 'arm64': 'aarch64'}[arch], 'Native host required'
name = 'statamic-qa-' + secrets.token_hex(5)
volume = name + '-data'
result = {'image': image, 'platform': 'linux/' + arch, 'host_machine': platform.machine(), 'emulated': False, 'gates': {}}

def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()

def gate(key):
    result['gates'][key] = 'passed'
    print(key + ': passed', flush=True)

def ready():
    for _ in range(120):
        state = json.loads(docker('inspect', name))[0]['State']
        if state.get('Health', {}).get('Status') == 'healthy':
            return
        if not state['Running']:
            raise AssertionError('Container stopped')
        time.sleep(2)
    raise AssertionError('Health timeout')

with tempfile.TemporaryDirectory(prefix=name) as tmp:
    tmp = Path(tmp)
    password = secrets.token_urlsafe(32)
    email = 'qualification@example.com'
    key = 'base64:' + base64.b64encode(secrets.token_bytes(32)).decode()
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(tmp/'key.pem'), '-out', str(tmp/'cert.pem'), '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    class Proxy(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            headers = dict(self.headers)
            headers['X-Forwarded-Proto'] = 'https'
            headers['X-Forwarded-Host'] = self.headers['Host']
            headers['Connection'] = 'close'
            conn = http.client.HTTPConnection('127.0.0.1', backend_port, timeout=120)
            conn.request(self.command, self.path, body=body, headers=headers)
            response = conn.getresponse()
            data = response.read()
            self.send_response(response.status)
            for k, v in response.getheaders():
                if k.lower() not in ('transfer-encoding', 'connection', 'content-length'):
                    self.send_header(k, v)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            conn.close()
        do_POST = do_GET
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tmp/'cert.pem', tmp/'key.pem')
    server.socket = context.wrap_socket(server.socket, server_side=True)
    base = 'https://localhost:' + str(server.server_port)
    env = tmp/'runtime.env'
    env.write_text('\n'.join(['APP_KEY='+key, 'APP_URL='+base, 'STATAMIC_ADMIN_EMAIL='+email, 'STATAMIC_ADMIN_PASSWORD='+password, 'SESSION_SECURE_COOKIE=true', 'STATAMIC_PRO_ENABLED=false']))
    env.chmod(0o600)
    def start():
        global backend_port
        docker('run', '-d', '--name', name, '--label', 'statamic.runtime.qa='+name, '--env-file', str(env), '-p', '127.0.0.1::80', '-v', volume+':/data', image)
        backend_port = int(docker('port', name, '80/tcp').rsplit(':', 1)[1])
        ready()
    def login():
        s = requests.Session()
        s.verify = str(tmp/'cert.pem')
        r = s.get(base+'/cp/auth/login', timeout=120)
        assert r.status_code == 200
        headers = {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest', 'X-XSRF-TOKEN': urllib.parse.unquote(s.cookies.get('XSRF-TOKEN'))}
        r = s.post(base+'/cp/auth/login', data={'email':email, 'password':password}, headers=headers, timeout=120)
        assert r.status_code == 200, 'Login failed'
        r = s.get(base+'/cp', timeout=120)
        assert r.status_code == 200 and '/auth/login' not in r.url
        assert any(c.secure for c in s.cookies if 'session' in c.name.lower()), 'Secure session cookie missing'
        headers['X-XSRF-TOKEN'] = urllib.parse.unquote(s.cookies.get('XSRF-TOKEN'))
        return s, headers
    # Small valid PNG, deterministic media readback.
    payload = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=')
    def readback():
        s, headers = login()
        r = s.get(base+'/cp/collections/pages/entries/'+entry_id, headers={'Accept':'application/json'}, timeout=120)
        assert r.status_code == 200 and 'Native architecture qualification' in r.text
        r = s.get(base+'/assets/qualification.png', timeout=30)
        assert r.status_code == 200 and hashlib.sha256(r.content).digest() == hashlib.sha256(payload).digest()
        s.close()
    try:
        docker('pull', '--platform', 'linux/'+arch, image)
        cfg = json.loads(docker('image', 'inspect', image))[0]
        assert cfg['Architecture'] == arch
        result['image_id'] = cfg['Id']
        result['config'] = {k:cfg['Config'].get(k) for k in ('User', 'Entrypoint', 'Cmd', 'Healthcheck')}
        gate('native_image_config')
        docker('volume', 'create', volume)
        start()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        gate('fresh_startup_health')
        r = requests.get(base+'/up', verify=str(tmp/'cert.pem'), timeout=30)
        assert r.status_code == 200
        r = requests.get(base+'/cp', verify=str(tmp/'cert.pem'), timeout=30)
        assert '/auth/login' in r.url
        s, headers = login()
        gate('https_secure_admin_login_and_anonymous_denial')
        r = s.get(base+'/cp/collections/pages/entries/create/default', headers={'Accept':'application/json'}, timeout=120)
        assert r.status_code == 200
        blueprint = r.json()['blueprint']['handle']
        r = s.post(base+'/cp/collections/pages/entries/default', json={'title':'Native architecture qualification', 'slug':'native-qualification', '_blueprint':blueprint, 'published':True, 'content':'Synthetic native runtime marker.'}, headers=headers, timeout=120)
        assert r.status_code == 200
        entry_id = r.json()['data']['id']
        r = s.post(base+'/cp/assets', data={'container':'assets','folder':'/'}, files={'file':('qualification.png',payload,'image/png')}, headers=headers, timeout=120)
        assert r.status_code == 200
        s.close()
        readback()
        gate('content_media_create_read')
        docker('restart', name)
        ready()
        readback()
        gate('restart_fresh_login_content_media')
        old_id = docker('inspect', '--format', '{{.Id}}', name)
        docker('rm', '-f', name)
        start()
        assert docker('inspect', '--format', '{{.Id}}', name) != old_id
        readback()
        gate('recreation_fresh_login_content_media')
        docker('stop', name)
        docker('run', '--rm', '--entrypoint', 'tar', '-v', volume+':/data:ro', '-v', str(tmp)+':/backup', image, 'czf', '/backup/data.tar.gz', '-C', '/data', '.')
        docker('rm', name)
        docker('volume', 'rm', volume)
        docker('volume', 'create', volume)
        docker('run', '--rm', '--entrypoint', 'sh', '-v', volume+':/data', '-v', str(tmp)+':/backup:ro', image, '-ec', 'test -z "$(ls -A /data)"; tar xzf /backup/data.tar.gz -C /data')
        start()
        readback()
        gate('stopped_backup_empty_volume_restore_fresh_login_content_media')
        logs = docker('logs', name)
        assert password not in logs and key not in logs
        gate('no_credentials_in_application_logs')
        result['media_sha256'] = hashlib.sha256(payload).hexdigest()
    finally:
        subprocess.run(['docker','rm','-f',name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['docker','volume','rm',volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        server.server_close()
        assert not docker('ps','-aq','--filter','label=statamic.runtime.qa='+name)
        assert volume not in docker('volume','ls','--format','{{.Name}}').splitlines()
        gate('disposable_container_volume_cleanup')
        Path(output).write_text(json.dumps(result, indent=2)+'\n')

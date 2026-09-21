#!/usr/bin/env python3
"""Anonymous full-blob registry verification and fail-closed tag guard."""
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request

repo = 'neobuilds/statamic'
version = sys.argv[-1]
assert re.fullmatch(r'6\.33\.0-xcloud\.[0-9]+', version)
root = 'https://ghcr.io/v2/' + repo
with urllib.request.urlopen('https://ghcr.io/token?service=ghcr.io&scope=repository:'+repo+':pull') as response:
    token = json.load(response)['token']
headers = {'Authorization':'Bearer '+token, 'Accept':'application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'}
def get(path):
    return urllib.request.urlopen(urllib.request.Request(root+path, headers=headers), timeout=120)
try:
    response = get('/manifests/'+version)
except urllib.error.HTTPError as error:
    if '--absent' in sys.argv and error.code == 404:
        print('Immutable tag absent; publication allowed')
        sys.exit(0)
    raise
assert '--absent' not in sys.argv, 'Refusing to overwrite existing immutable tag'
raw = response.read()
digest = 'sha256:'+hashlib.sha256(raw).hexdigest()
assert response.headers['Docker-Content-Digest'] == digest
index = json.loads(raw)
platforms = {m['platform']['architecture']:m for m in index['manifests'] if m.get('platform',{}).get('os') == 'linux'}
assert set(platforms) == {'amd64','arm64'}
result = {'tag':version, 'index_digest':digest, 'anonymous':True, 'platforms':{}}
verified = set()
for arch, descriptor in platforms.items():
    raw = get('/manifests/'+descriptor['digest']).read()
    assert 'sha256:'+hashlib.sha256(raw).hexdigest() == descriptor['digest']
    manifest = json.loads(raw)
    for blob in [manifest['config'], *manifest['layers']]:
        if blob['digest'] in verified:
            continue
        h = hashlib.sha256()
        size = 0
        data = bytearray() if blob is manifest['config'] else None
        with get('/blobs/'+blob['digest']) as stream:
            while chunk := stream.read(1024*1024):
                h.update(chunk)
                size += len(chunk)
                if data is not None:
                    data.extend(chunk)
        assert size == blob['size'] and 'sha256:'+h.hexdigest() == blob['digest']
        verified.add(blob['digest'])
        if data is not None:
            config = json.loads(data)
    assert config['architecture'] == arch and config['os'] == 'linux'
    result['platforms'][arch] = {'manifest_digest':descriptor['digest'], 'config_digest':manifest['config']['digest'], 'blob_count':len(manifest['layers'])+1, 'config':{k:config['config'].get(k) for k in ('User','Entrypoint','Cmd','Healthcheck')}}
result['unique_verified_blobs'] = len(verified)
print(json.dumps(result, indent=2))

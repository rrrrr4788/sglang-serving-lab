import json
import os
import re
import sys
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    key = os.environ['GATEWAY_API_KEY']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    def get(base, path):
        authenticated = base == 'http://127.0.0.1:8080' or (len(sys.argv) > 1 and base == sys.argv[1])
        headers = {'Authorization':'Bearer '+key} if authenticated else {}
        req = urllib.request.Request(base+path, headers=headers)
        try:
            with opener.open(req,timeout=5) as response: return response.status,response.read()
        except urllib.error.HTTPError as error:
            status=error.code;error.close();return status,b''
    def data(base,path):
        status,raw=get(base,path)
        if status!=200: raise RuntimeError('Private observation endpoint unavailable')
        return json.loads(raw)
    gateway='http://127.0.0.1:8080'
    status,_=get(gateway,'/readiness')
    workers=data(gateway,'/workers')['workers']
    healthy=sorted(x['url'].rstrip('/') for x in workers if x.get('is_healthy') is True)
    prom='http://sglang-prometheus:9090'
    rules=[rule for group in data(prom,'/api/v1/rules')['data']['groups'] for rule in group['rules'] if rule.get('name')=='SGLangNoReadyWorker']
    assert len(rules)==1, 'Expected exactly one loaded SGLangNoReadyWorker rule'
    receiver=data('http://sglang-alert-receiver:8080','/events')
    am_status,_=get('http://sglang-alertmanager:9093','/-/ready')
    value={'gateway_status':status,'healthy_urls':healthy,'rule_state':rules[0]['state'],
           'rule_health':rules[0]['health'],'alertmanager_status':am_status,'receiver':receiver}
    if len(sys.argv)>1:
        old=sys.argv[1]
        try:
            health,_=get(old,'/health')
            code,raw=get(old,'/metrics')
            samples=re.findall(r'^sglang:num_running_reqs(?:\{[^\n]*\})?\s+([-+\deE.]+)(?:\s+\d+)?$',raw.decode(),re.M) if code==200 else []
            value['old']={'health':health,'running':sum(float(x) for x in samples) if samples else None}
        except (OSError,urllib.error.URLError): value['old']={'health':None,'running':None}
    print(json.dumps(value),flush=True)


if __name__=='__main__': main()

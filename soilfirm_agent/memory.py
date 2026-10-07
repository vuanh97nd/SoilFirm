"""Trusted HTTPS memory endpoint; server keeps Cloudflare KV credentials."""
from urllib.parse import urlsplit
import requests

class MemoryClient:
    def __init__(self,url,token,session=None):
        if urlsplit(url).scheme!='https' or not token:raise ValueError('Memory requires HTTPS and a bearer token')
        self.url=url;self.token=token;self.session=session or requests.Session();self.session.trust_env=False
    def request(self,payload):
        response=self.session.post(self.url,json=payload,headers={'Authorization':'Bearer '+self.token},timeout=(4,12),allow_redirects=False,stream=True)
        try:
            if response.status_code!=200:raise RuntimeError('Memory HTTP '+str(response.status_code))
            data=bytearray()
            for chunk in response.iter_content(16384):
                data.extend(chunk)
                if len(data)>1024*1024:raise ValueError('Memory response too large')
            import json
            return json.loads(data)
        finally:response.close()
    def __call__(self,query,limit):
        records=self.request({'op':'search','query':query[:500],'limit':min(limit,20)}).get('records')
        if not isinstance(records,list):raise ValueError('Memory response requires records array')
        return records[:limit]
    def upsert(self,record):
        result=self.request({'op':'upsert','record':record})
        if result.get('stored') is not True:raise ValueError('Memory server did not confirm storage')
        return result

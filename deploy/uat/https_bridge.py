"""Prepared only. Fixed loopback bridge; never starts on import, no DB/LINE calls."""
import argparse,json,re
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI,Request
from starlette.responses import Response,StreamingResponse
from starlette.background import BackgroundTask

UPSTREAM='http://127.0.0.1:8151'
MAX_BODY=32*1024*1024
HOP={'connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade'}
DIST=Path(__file__).resolve().parents[2]/'frontend/dist'
STATIC_FILES=frozenset('/assets/'+p.relative_to(DIST/'assets').as_posix() for p in (DIST/'assets').rglob('*') if p.is_file() and not p.is_symlink() and p.suffix in {'.js','.css','.woff','.woff2','.png','.svg','.ico'})
UUID=r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
OPAQUE=r'[A-Za-z0-9_.~-]+'
# Caregiver surface only. Admin, dev, fieldtest, grants, MPC/review,
# emergency, Web Push, documents/config files and all unknown routes deny.
ROUTES=[
    ({'GET','HEAD'},r'/liff(?:/(?:ask|bind|help|record|cases|report|report/entry|report/preview|service-clients))?/?'),
    ({'GET','HEAD'},rf'/liff/(?:answers|record|cases)/{UUID}/?'),
    ({'GET','HEAD'},rf'/liff/service-clients/{UUID}/service-forms/[A-Za-z0-9_-]+/?'),
    ({'GET','HEAD'},r'/api/(?:healthz|config/public|me|categories|stats/mine|documents/coverage|qa/history|cases/mine|transcripts)'),
    ({'POST'},r'/api/auth/(?:liff|liff/bind|logout)'),
    ({'POST'},r'/api/(?:qa/ask|cases|audio/uploads)'),
    ({'GET'},rf'/api/(?:qa|cases|transcripts)/{UUID}'),
    ({'POST'},rf'/api/qa/{UUID}/(?:escalate|retry-escalation|feedback|tts)'),
    ({'GET'},rf'/api/qa/{UUID}/tts'),
    ({'POST'},rf'/api/cases/{UUID}/messages'),
    ({'POST'},rf'/api/transcripts/{UUID}/(?:confirm|retry)'),
    ({'DELETE'},rf'/api/transcripts/{UUID}'),
    ({'GET'},rf'/api/sources/chunks/{UUID}'),
    ({'GET'},rf'/api/sources/versions/{UUID}/file'),
    ({'POST'},rf'/api/sources/versions/{UUID}/download-url'),
    ({'GET'},rf'/api/(?:media/tts|sources/download)/{OPAQUE}'),
    ({'GET','POST'},r'/api/quality/qa/'+UUID+r'/feedback'),
    ({'GET'},r'/api/jiaan1030/service-catalog'),
    ({'GET','POST'},r'/api/jiaan1030/(?:service-clients|service-drafts)'),
    ({'PATCH'},rf'/api/jiaan1030/service-drafts/{UUID}'),
    ({'POST'},rf'/api/jiaan1030/service-drafts/{UUID}/submit'),
]

def route_allowed(method,path):
    if '%' in path or '\\' in path or '//' in path or any(s.startswith('.') for s in path.split('/') if s):return False
    if method in {'GET','HEAD'} and path in STATIC_FILES:return True
    return any(method in methods and re.fullmatch(pattern,path) for methods,pattern in ROUTES)

def create_app(origin,transport=None):
    if not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com',origin):
        raise ValueError('UAT_BRIDGE_DEDICATED_ORIGIN_REQUIRED')
    host=origin.removeprefix('https://')
    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(transport=transport,follow_redirects=False,trust_env=False,timeout=httpx.Timeout(120,connect=5)) as client:
            app.state.client=client
            yield
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    @app.api_route('/{path:path}',methods=['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'])
    async def forward(request:Request,path:str):
        if request.headers.get('host','').lower()!=host:
            return Response(status_code=421)
        if request.method in {'GET','HEAD'} and request.url.path=='/':
            return Response(status_code=307,headers={'Location':'/liff','Cache-Control':'no-store'})
        if not route_allowed(request.method,request.url.path):
            return Response(status_code=404)
        if request.headers.get('upgrade'):
            return Response(status_code=400)
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>MAX_BODY:return Response(status_code=413)
            chunks.append(chunk)
        nominated={x.strip().lower() for x in request.headers.get('connection','').split(',')}
        headers={k:v for k,v in request.headers.items() if k.lower() not in HOP|nominated|{'host','content-length','forwarded','x-internal-health-token'} and not k.lower().startswith('x-forwarded-')}
        headers.update({'host':host,'x-forwarded-proto':'https','x-forwarded-host':host,'x-forwarded-for':'127.0.0.1'})
        raw_path=request.scope.get('raw_path',request.url.path.encode()).split(b'?',1)[0]
        if not raw_path.startswith(b'/') or raw_path.startswith(b'//'):
            return Response(status_code=400)
        url=httpx.URL(UPSTREAM).copy_with(raw_path=raw_path+(b'?'+request.scope['query_string'] if request.scope['query_string'] else b''))
        try:
            upstream=await app.state.client.send(app.state.client.build_request(request.method,url,headers=headers,content=b''.join(chunks)),stream=True)
        except httpx.HTTPError:
            return Response('UAT temporarily unavailable',status_code=502,headers={'Cache-Control':'no-store'})
        response=StreamingResponse(upstream.aiter_raw(),status_code=upstream.status_code,background=BackgroundTask(upstream.aclose))
        nominated={x.strip().lower() for x in upstream.headers.get('connection','').split(',')}
        response.raw_headers=[(k.encode('latin-1'),v.encode('latin-1')) for k,v in upstream.headers.multi_items() if k.lower() not in HOP|nominated]
        return response
    return app

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--active-file',required=True)
    parser.add_argument('--launch',action='store_true')
    args=parser.parse_args()
    state=json.loads(Path(args.active_file).read_text(encoding='utf-8-sig'))
    if state['Origin']!='http://127.0.0.1:18551' or state.get('StoppedAt'):
        raise RuntimeError('UAT_BRIDGE_ACTIVE_RECORD_MISMATCH')
    app=create_app(state['PublicUrl'])
    if not args.launch:
        print('CHECK ONLY: fixed 18551 -> 8151 bridge prepared; no listener started')
    else:
        import uvicorn
        uvicorn.run(app,host='127.0.0.1',port=18551,access_log=False,proxy_headers=False,log_level='warning')

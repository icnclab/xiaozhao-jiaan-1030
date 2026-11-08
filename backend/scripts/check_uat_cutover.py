"""Offline by default. --live performs only local GET checks after approved launch."""
import argparse,json,os,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def check(env_file,live=False,public=False):
    os.environ['LTC_PROFILE']='uat';os.environ['LTC_UAT_ENV_FILE']=str(Path(env_file).resolve())
    from app.config import get_settings
    get_settings.cache_clear();s=get_settings()
    from app.uat import push_allowed
    from app.services.jiaan_emergency_dispatch import is_enabled
    from app.services.jiaan_webpush import enabled,public_key
    assert s.is_uat and s.line_mode=='real' and s.uat_outbound_mode=='blocked'
    assert not is_enabled() and not enabled() and public_key()==''
    assert all(not push_allowed(s,x) for x in s.uat_line_user_ids)
    assert (Path(__file__).resolve().parents[2]/'frontend/dist/index.html').is_file()
    result={'offline_settings':'PASS','notifications_blocked':True,'emergency_dispatch':False,'webpush':False,'frontend_build_present':True,'allowlisted_tester_count':len(s.uat_line_user_ids),'live_checks':'NOT_RUN'}
    if live:
        def get(path,token=False):
            headers={'X-Internal-Health-Token':s.internal_health_token} if token else {}
            with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8151'+path,headers=headers),timeout=8) as r:
                assert r.status==200
                return json.load(r)
        health=get('/api/healthz',True)
        assert health['db']=='ok' and health['database_name']=='ltc_demo' and health['modes']['line']=='real'
        config=get('/api/config/public')
        assert config['liff_id']==s.liff_id and config['line_mode']=='real' and not config['dev_features']
        assert health['worker_heartbeat_age_sec'] is not None and health['worker_heartbeat_age_sec']<90
        result['live_checks']='PASS'
        if public:
            with urllib.request.urlopen(s.public_base_url+'/api/config/public',timeout=8) as r:
                config=json.load(r)
                assert config['liff_id']==s.liff_id and config['line_mode']=='real' and not config['dev_features']
            with urllib.request.urlopen(s.public_base_url+'/api/healthz',timeout=8) as r:
                health=json.load(r);assert 'database_name' not in health and 'modes' not in health
            with urllib.request.urlopen(s.public_base_url+'/liff',timeout=8) as r:
                assert r.status==200 and 'text/html' in r.headers.get('Content-Type','')
            try:urllib.request.urlopen(s.public_base_url+'/api/line/webhook',timeout=8)
            except urllib.error.HTTPError as exc:assert exc.code==404
            else:raise RuntimeError('UAT_WEBHOOK_MUST_REMAIN_BLOCKED')
            result['public_checks']='PASS'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--env-file',required=True);p.add_argument('--live',action='store_true');p.add_argument('--public',action='store_true');a=p.parse_args()
    try:
        if a.public and not a.live:raise RuntimeError('UAT_PUBLIC_CHECK_REQUIRES_LIVE')
        print(json.dumps(check(a.env_file,a.live,a.public)))
    except Exception as exc:
        print('NOT_READY: '+type(exc).__name__);raise SystemExit(2)

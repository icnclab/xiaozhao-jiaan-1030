"""Scoped offline UAT tests. No root tests/conftest, DB, LINE or service access."""
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.engine import URL

from app.config import get_settings, Settings
from app import uat

USER = "U" + "a" * 32
OTHER = "U" + "b" * 32

@pytest.fixture(autouse=True)
def cfg(tmp_path, monkeypatch):
    baseline=tmp_path/"baseline.json"
    baseline.write_text(json.dumps({"version":1,"database_password":uat.fingerprint("production-db-unit-only"),"fields":{key:uat.fingerprint("production-unit-only-"+key) for key in uat.PROTECTED_FIELDS},"origins":[uat.fingerprint("https://production.test")],"data_dirs":[uat.fingerprint(str(tmp_path/"data_clean"))]}))
    values={
        "APP_ENV":"uat", "LINE_MODE":"real",
        "DATABASE_URL":URL.create("postgresql+psycopg",username="ltc_uat_app",password="unit-only",host="localhost",database="ltc_demo").render_as_string(hide_password=False),
        "DATA_DIR":str(tmp_path/"data_demo"), "PUBLIC_BASE_URL":"https://uat.test",
        "UAT_PRODUCTION_FINGERPRINTS_FILE":str(baseline),
        "SECRET_KEY":"unit-only-uat-application-key-"+"x"*32,
        "DATA_ENCRYPTION_KEY":Fernet.generate_key().decode(),
        "INTERNAL_HEALTH_TOKEN":"unit-only-uat-health-"+"x"*32,
        "LINE_LOGIN_CHANNEL_ID":"9000000001", "LIFF_ID":"9000000001-unit",
        "LINE_CHANNEL_SECRET":"unit-uat-channel-secret", "LINE_CHANNEL_ACCESS_TOKEN":"unit-uat-channel-access",
        "UAT_LINE_USER_IDS":USER,
        "UAT_ACCOUNT_ROLES":json.dumps({"cg_happy_1":"caregiver","sup_happy_a":"supervisor","director_happy":"director"}),
        "UAT_OUTBOUND_MODE":"blocked",
    }
    path=tmp_path/"uat.local.env"
    def save():
        path.write_text("\n".join(k+"="+v for k,v in values.items())+"\n",encoding="utf-8")
        get_settings.cache_clear()
    save()
    monkeypatch.setenv("LTC_PROFILE","uat")
    monkeypatch.setenv("LTC_UAT_ENV_FILE",str(path))
    def forbidden(*a,**k): raise AssertionError("Real HTTP is forbidden in offline tests")
    monkeypatch.setattr(httpx,"post",forbidden)
    yield SimpleNamespace(values=values,path=path,save=save,baseline=baseline)
    get_settings.cache_clear()


def test_uat_loads_only_explicit_file_not_process_or_dotenv(cfg,monkeypatch):
    monkeypatch.setenv("DATABASE_URL","production-value-must-not-load")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN","production-value-must-not-load")
    monkeypatch.setenv("DATA_DIR","data_clean")
    s=get_settings()
    assert s.is_uat and s.database_url==cfg.values["DATABASE_URL"]
    assert s.line_channel_access_token==cfg.values["LINE_CHANNEL_ACCESS_TOKEN"]
    assert not s.dev_features_enabled and not s.api_docs_enabled

@pytest.mark.parametrize("field",uat.PROTECTED_FIELDS)
def test_shared_production_value_is_rejected(cfg,field):
    cfg.values[field.upper()]="production-unit-only-"+field
    cfg.save()
    with pytest.raises(RuntimeError,match="UAT_MISSING_OR_SHARED"):
        get_settings()

@pytest.mark.parametrize("field,value",[
    ("APP_ENV","production"),("LINE_MODE","mock"),
    ("PUBLIC_BASE_URL","https://production.test"),("PUBLIC_BASE_URL","http://uat.test"),
    ("PUBLIC_BASE_URL","https://uat.test/formal/path"),("PUBLIC_BASE_URL","https://uat.invalid"),
    ("LIFF_ID","9000000002-other"),("UAT_LINE_USER_IDS",""),
    ("UAT_LINE_USER_IDS","U-not-a-real-id"),("UAT_ACCOUNT_ROLES",'{}'),
    ("UAT_OUTBOUND_MODE","all"),("SECRET_KEY","short"),
    ("DATA_ENCRYPTION_KEY","invalid"),
])
def test_unsafe_config_rejected(cfg,field,value):
    cfg.values[field]=value;cfg.save()
    with pytest.raises((RuntimeError,ValueError)):
        get_settings()

@pytest.mark.parametrize("database,user,query",[
    ("ltc_clean","ltc_uat_app",{}),("ltc_test","ltc_uat_app",{}),
    ("ltc_demo","postgres",{}),("ltc_demo","ltc_uat_app",{"user":"postgres"}),
    ("ltc_demo","ltc_uat_app",{"options":"-c role=postgres"}),
])
def test_db_url_override_rejected(cfg,database,user,query):
    cfg.values["DATABASE_URL"]=URL.create("postgresql+psycopg",username=user,password="unit-only",host="localhost",database=database,query=query).render_as_string(hide_password=False)
    cfg.save()
    with pytest.raises(RuntimeError):get_settings()


def test_missing_baseline_rejected(cfg):
    cfg.values["UAT_PRODUCTION_FINGERPRINTS_FILE"]=str(cfg.path.parent/"absent.json");cfg.save()
    with pytest.raises(RuntimeError,match="BASELINE_REQUIRED"):get_settings()


def test_missing_dedicated_file_never_falls_back_to_root_env(cfg,monkeypatch):
    monkeypatch.setenv("LTC_UAT_ENV_FILE",str(cfg.path.parent/"absent.env"))
    with pytest.raises(RuntimeError,match="DEDICATED"):get_settings()


def test_unknown_config_and_environment_interpolation_rejected(cfg):
    cfg.values["UNKNOWN_SETTING"]="value";cfg.save()
    with pytest.raises(RuntimeError,match="UNKNOWN"):get_settings()
    del cfg.values["UNKNOWN_SETTING"]
    cfg.values["SECRET_KEY"]="${SECRET_KEY}";cfg.save()
    with pytest.raises(RuntimeError,match="INTERPOLATION"):get_settings()


def test_formal_data_directory_rejected(cfg):
    cfg.values["DATA_DIR"]=str(cfg.path.parent/"data_clean");cfg.save()
    with pytest.raises(RuntimeError,match="DIRECTORY_FORBIDDEN"):get_settings()

@pytest.mark.parametrize("row",[("ltc_clean","ltc_uat_app",False),("ltc_demo","postgres",True),("ltc_demo","ltc_uat_app",True)])
def test_runtime_database_guard_rejects_wrong_db_or_privilege(row):
    cursor=Mock();cursor.fetchone.return_value=row
    with pytest.raises(RuntimeError,match="RUNTIME_GUARD"):uat.verify_db_cursor(cursor)
    assert cursor.execute.call_args.args[0].lstrip().startswith("SELECT")


def test_runtime_database_guard_accepts_safe_identity():
    cursor=Mock();cursor.fetchone.return_value=("ltc_demo","ltc_uat_app",False)
    uat.verify_db_cursor(cursor)


def test_configure_engine_cannot_override_profile_dsn(cfg,monkeypatch):
    from app import db
    create=Mock(side_effect=AssertionError("No engine creation allowed"));monkeypatch.setattr(db,"create_engine",create)
    with pytest.raises(RuntimeError,match="OVERRIDE_FORBIDDEN"):db._create_checked_engine("another-url")
    create.assert_not_called()

@pytest.mark.parametrize("host,origin,path,method,expected",[
    ("uat.test",None,"/liff","GET",True),
    ("production.test",None,"/liff","GET",False),
    ("uat.test","https://production.test","/api/auth/login","POST",False),
    ("uat.test","https://uat.test","/api/auth/login","POST",True),
    ("127.0.0.1:8151",None,"/api/healthz","GET",True),
    ("127.0.0.1:8151",None,"/api/auth/login","POST",False),
])
def test_origin_and_callback_isolation(cfg,host,origin,path,method,expected):
    assert uat.request_allowed(get_settings(),host,origin,path,method)==expected

@pytest.mark.parametrize("source",[{"type":"user","userId":OTHER},{"type":"group","userId":USER},{"type":"room","userId":USER},{}])
def test_unapproved_webhook_source_rejected(cfg,source):
    with pytest.raises(RuntimeError,match="SOURCE_NOT_ALLOWED"):
        uat.check_webhook(get_settings(),{"events":[{"source":source}]})


def test_allowed_webhook_and_empty_console_verification(cfg):
    s=get_settings();uat.check_webhook(s,{"events":[]});uat.check_webhook(s,{"events":[{"source":{"type":"user","userId":USER}}]})

@pytest.mark.parametrize("value",[[],None,{"events":"bad"}])
def test_malformed_webhook_rejected_without_storage(cfg,value):
    with pytest.raises(RuntimeError):uat.check_webhook(get_settings(),value)


def test_mock_identities_disabled_and_verified_audience_enforced(cfg,monkeypatch):
    from app import auth
    with pytest.raises(auth.AuthError) as error:
        auth.verify_liff_id_token("dev:"+USER)
    assert error.value.code == "dev_disabled"
    def response(audience,user):
        return SimpleNamespace(status_code=200,json=lambda:{"aud":audience,"exp":time.time()+600,"sub":user})
    monkeypatch.setattr(httpx,"post",lambda *a,**k:response("production-audience",USER))
    with pytest.raises(auth.AuthError):auth.verify_liff_id_token("unit-token")
    monkeypatch.setattr(httpx,"post",lambda *a,**k:response("9000000001",OTHER))
    with pytest.raises(auth.AuthError,match="UAT identity"):auth.verify_liff_id_token("unit-token")
    monkeypatch.setattr(httpx,"post",lambda *a,**k:response("9000000001",USER))
    assert auth.verify_liff_id_token("unit-token").line_user_id==USER


def test_unlisted_account_or_changed_role_cannot_issue_session(cfg):
    from app import auth
    db=Mock()
    for name,role in [("not-listed","caregiver"),("cg_happy_1","admin")]:
        with pytest.raises(auth.AuthError):auth.issue_session(db,SimpleNamespace(username=name,role=role,is_active=True),"web")
    db.add.assert_not_called()


def test_outbound_default_blocks_push_reply_and_line_download(cfg):
    from app.line.client import RealLineClient,ContentUnavailable
    client=RealLineClient(get_settings().line_channel_access_token)
    assert client.push(USER,[],"unit-retry").error_code=="uat_push_blocked"
    assert client.reply("unit-reply-token",[]).error_code=="uat_reply_disabled"
    with pytest.raises(ContentUnavailable):client.get_content("12345")


def test_opt_in_push_only_allows_explicit_test_recipient(cfg,monkeypatch):
    cfg.values["UAT_OUTBOUND_MODE"]="allowlist";cfg.save()
    from app.line.client import RealLineClient
    send=Mock(return_value=SimpleNamespace(status_code=200));monkeypatch.setattr(httpx,"post",send)
    client=RealLineClient(get_settings().line_channel_access_token)
    assert not client.push(OTHER,[],"unit-retry").accepted
    send.assert_not_called()
    assert client.push(USER,[],"unit-retry").accepted
    assert send.call_args.kwargs["json"]["to"]==USER
    assert send.call_count==1


def test_inherited_emergency_and_webpush_flags_cannot_enable_uat(cfg,monkeypatch):
    monkeypatch.setenv("JIAAN_EMERGENCY_LINE_DISPATCH","on");monkeypatch.setenv("JIAAN_WEBPUSH_DISPATCH","on")
    from app.services import jiaan_webpush,jiaan_emergency_dispatch
    assert not jiaan_webpush.enabled() and not jiaan_emergency_dispatch.is_enabled()
    assert jiaan_webpush.public_key()==""
    from app.api.jiaan_webpush_routes import manager
    from fastapi import HTTPException
    with pytest.raises(HTTPException):manager(SimpleNamespace(role="director"))


def test_preexisting_emergency_job_is_skipped_without_db_lookup(cfg):
    from app.services import notifications
    job=SimpleNamespace(status="queued",payload={"kind":"jiaan_emergency_alert"})
    db=Mock();db.get.return_value=job
    assert notifications.send(db,"unit-job")== (True,False)
    assert job.status=="skipped" and job.last_error_code=="uat_emergency_disabled"
    db.scalar.assert_not_called()


def test_uat_http_policy_rejects_wrong_host_before_any_db(cfg):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import get_db
    def forbidden_db():raise AssertionError("DB dependency must not run")
    app.dependency_overrides[get_db]=forbidden_db
    try:
        client=TestClient(app,base_url="https://production.test")
        assert client.post("/api/auth/login",json={"username":"x","password":"x"}).status_code==403
        client=TestClient(app,base_url="https://uat.test")
        public=client.get("/api/config/public").json()
        assert public["line_mode"]=="real" and public["dev_features"] is False
        assert public["liff_id"]=="9000000001-unit"
    finally:app.dependency_overrides.clear()


def test_webhook_foreign_signature_and_unknown_source_never_store(cfg,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import get_db
    from app.api import line_routes
    from app.line.signature import compute_signature
    db=Mock();app.dependency_overrides[get_db]=lambda:db
    store=Mock(return_value=(0,0));monkeypatch.setattr(line_routes.line_service,"store_events",store)
    monkeypatch.setattr(line_routes.audit,"record",Mock())
    client=TestClient(app,base_url="https://uat.test")
    try:
        body=json.dumps({"events":[{"source":{"type":"user","userId":OTHER}}]}).encode()
        assert client.post("/api/line/webhook",content=body,headers={"x-line-signature":compute_signature("unit-production-secret",body)}).status_code==401
        assert client.post("/api/line/webhook",content=body,headers={"x-line-signature":compute_signature(get_settings().line_channel_secret,body)}).status_code==403
        store.assert_not_called()
    finally:app.dependency_overrides.clear()


def test_non_uat_behavior_properties_unchanged(cfg):
    s=Settings(_env_file=None,database_url="unit-test-only",app_env="production")
    assert not s.is_uat and not s.api_docs_enabled and not s.dev_features_enabled
    dev=Settings(_env_file=None,database_url="unit-test-only",app_env="dev",line_mode="mock")
    assert dev.dev_features_enabled and dev.api_docs_enabled
    assert uat.push_allowed(s,OTHER) and uat.request_allowed(s,"production.test",None,"/liff","GET")


def test_cli_static_check_and_safe_errors(cfg,capsys):
    path=Path(__file__).resolve().parents[1]/"scripts/check_uat_env.py"
    spec=importlib.util.spec_from_file_location("uat_check_cli",path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    assert mod.main(["--env-file",str(cfg.path)])==0
    cfg.values["DATABASE_URL"]="invalid-url";cfg.save()
    assert mod.main(["--env-file",str(cfg.path)])==2
    assert "invalid-url" not in capsys.readouterr().out


@pytest.mark.parametrize("mode,code",[("denied",None),("allowed","UAT_CAN_CONNECT_OTHER_DATABASE"),("network","UAT_DATABASE_DENIAL_NOT_VERIFIED"),("roster","UAT_ROSTER_NOT_READY")])
def test_readonly_preflight_requires_real_cross_db_denial(cfg,monkeypatch,mode,code):
    from app import uat_preflight
    from sqlalchemy.exc import DBAPIError
    statements=[]
    rows=[{"username":n,"role":role,"is_active":True,"org_id":"unit-org"} for n,role in get_settings().uat_account_roles.items()]
    if mode=="roster":rows=[]
    class Result:
        def __init__(self,value):self.value=value
        def scalar_one(self):return self.value
        def mappings(self):return self
        def all(self):return self.value
    class Connection:
        connection=SimpleNamespace(cursor=lambda:SimpleNamespace(execute=lambda sql:statements.append(sql),fetchone=lambda:("ltc_demo","ltc_uat_app",False),close=lambda:None))
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,*args):
            statements.append(str(sql))
            return Result("on" if str(sql).startswith("SHOW") else False if "has_schema_privilege" in str(sql) else rows)
    class Engine:
        def __init__(self,db):self.db=db
        def connect(self):
            if self.db!="ltc_demo" and mode!="allowed":
                original=Exception("unit-only-denial");original.sqlstate="28000" if mode=="denied" else None
                raise DBAPIError(None,None,original)
            return Connection()
        def dispose(self):pass
    def factory(url,**kwargs):
        from sqlalchemy.engine import make_url
        assert "default_transaction_read_only=on" in kwargs["connect_args"]["options"]
        return Engine(make_url(url).database)
    monkeypatch.setattr(uat_preflight,"create_engine",factory)
    if code:
        with pytest.raises(RuntimeError,match=code):uat_preflight.check_database(get_settings())
    else:uat_preflight.check_database(get_settings())
    assert all(sql.lstrip().startswith(("SELECT","SHOW")) for sql in statements)


def test_baseline_contains_only_fingerprints_and_never_overwrites(cfg):
    path=Path(__file__).resolve().parents[1]/"scripts/check_uat_env.py"
    spec=importlib.util.spec_from_file_location("uat_baseline_cli",path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    output=cfg.path.parent/"new-baseline.json"
    mod.make_baseline(cfg.path,None,["https://production.test"],output)
    content=output.read_text();value=json.loads(content)
    assert all(len(x)==64 for x in value["fields"].values())
    assert cfg.values["LINE_CHANNEL_ACCESS_TOKEN"] not in content
    assert cfg.values["DATA_ENCRYPTION_KEY"] not in content
    with pytest.raises(RuntimeError,match="NEW_PRIVATE_BASELINE_PATH_REQUIRED"):
        mod.make_baseline(cfg.path,None,["https://production.test"],output)


def test_launcher_defaults_to_no_service_or_db_operation(cfg,monkeypatch,capsys):
    path=Path(__file__).resolve().parents[1]/"scripts/run_uat.py"
    spec=importlib.util.spec_from_file_location("uat_runner",path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    from app import uat_preflight
    check=Mock(side_effect=AssertionError("No DB check without explicit launch"));monkeypatch.setattr(uat_preflight,"check_database",check)
    execute=Mock(side_effect=AssertionError("No process execution"));monkeypatch.setattr(mod.os,"execve",execute)
    assert mod.main(["--kind","api","--env-file",str(cfg.path)])==0
    assert "CHECK ONLY" in capsys.readouterr().out
    check.assert_not_called();execute.assert_not_called()


def test_launcher_refuses_existing_8151_without_restart(cfg,monkeypatch):
    path=Path(__file__).resolve().parents[1]/"scripts/run_uat.py"
    spec=importlib.util.spec_from_file_location("uat_occupied_runner",path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    from app import uat_preflight
    monkeypatch.setattr(uat_preflight,"check_database",lambda s:None)
    class Socket:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def connect_ex(self,address):assert address==("127.0.0.1",8151);return 0
    monkeypatch.setattr(mod.socket,"socket",Socket)
    execute=Mock();monkeypatch.setattr(mod.os,"execve",execute)
    with pytest.raises(RuntimeError,match="OCCUPIED_NO_RESTART"):
        mod.main(["--kind","api","--env-file",str(cfg.path),"--launch"])
    execute.assert_not_called()


@pytest.mark.parametrize("identity,user,expected",[(OTHER,None,"uat_source_not_allowed"),(USER,SimpleNamespace(username="outside-roster",role="caregiver",is_active=True),"uat_account_not_allowed")])
def test_old_queued_line_events_are_guarded_before_decrypt_or_work(cfg,monkeypatch,identity,user,expected):
    from app.line import service
    event=SimpleNamespace(status="queued",line_user_id=identity,payload_encrypted="unit-old-encrypted-data")
    db=Mock();db.get.return_value=event
    monkeypatch.setattr(service,"_user_for",lambda *args:user)
    decrypt=Mock(side_effect=AssertionError("No old payload may be decrypted"));monkeypatch.setattr(service,"decrypt_json",decrypt)
    service.process_event(db,"unit-event")
    assert event.status=="ignored" and event.error==expected
    decrypt.assert_not_called()


def test_regular_notification_for_unlisted_account_is_skipped(cfg):
    from app.services import notifications
    job=SimpleNamespace(status="queued",payload={"kind":"case_reply"},recipient_id="unit-user")
    user=SimpleNamespace(username="outside-roster",role="caregiver",is_active=True)
    db=Mock();db.get.side_effect=[job,user]
    assert notifications.send(db,"unit-job")== (True,False)
    assert job.status=="skipped" and job.last_error_code=="uat_account_not_allowed"
    db.scalar.assert_not_called()


def test_binding_code_cannot_be_created_for_outside_roster(cfg):
    from app import auth
    db=Mock();user=SimpleNamespace(username="outside-roster",role="caregiver",is_active=True)
    with pytest.raises(auth.AuthError):auth.create_binding_code(db,user,user)
    db.add.assert_not_called()


@pytest.mark.parametrize("profile",["UAT","typo","default"])
def test_misspelled_or_missing_profile_never_reads_formal_defaults(cfg,monkeypatch,profile):
    monkeypatch.setenv("LTC_PROFILE",profile)
    with pytest.raises(RuntimeError):get_settings()


def test_uat_health_token_never_reads_or_writes_formal_token_file(cfg,monkeypatch,tmp_path):
    from app.services import health
    target=tmp_path/"must-not-exist"/"formal-token.txt"
    monkeypatch.setattr(health,"_TOKEN_FILE",target)
    monkeypatch.setattr(health,"_cached_token",None)
    assert health.ensure_internal_health_token()==cfg.values["INTERNAL_HEALTH_TOKEN"]
    assert not target.exists()

@pytest.mark.parametrize("endpoint,active,valid",[("https://uat.test/api/line/webhook",True,True),("https://production.test/api/line/webhook",True,False),("https://uat.test/api/line/webhook",False,False)])
def test_line_preflight_is_readonly_and_requires_uat_endpoint(cfg,monkeypatch,endpoint,active,valid):
    from app import uat_preflight
    import io
    calls=[]
    class Response(io.BytesIO):
        def __enter__(self):return self
        def __exit__(self,*args):self.close()
    def read(request,timeout):
        assert request.get_method()=="GET"
        assert request.full_url=="https://api.line.me/v2/bot/channel/webhook/endpoint"
        calls.append(request)
        return Response(json.dumps({"endpoint":endpoint,"active":active}).encode())
    monkeypatch.setattr(uat_preflight.urllib.request,"urlopen",read)
    if valid:uat_preflight.check_line(get_settings())
    else:
        with pytest.raises(RuntimeError,match="ROUTE_NOT_READY"):uat_preflight.check_line(get_settings())
    assert len(calls)==1


def test_new_private_config_generates_new_keys_without_production_reads(cfg,capsys):
    from dotenv import dotenv_values
    path=Path(__file__).resolve().parents[1]/"scripts/init_uat_private.py"
    spec=importlib.util.spec_from_file_location("uat_private_init",path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    target=cfg.path.parent/"new-private"/"uat.local.env"
    assert mod.main(["--output",str(target)])==0
    values=dotenv_values(target)
    assert len(values["SECRET_KEY"])==64
    assert len(values["INTERNAL_HEALTH_TOKEN"])==64
    assert values["LINE_CHANNEL_ACCESS_TOKEN"].startswith("REPLACE_")
    output=capsys.readouterr().out
    assert values["SECRET_KEY"] not in output and values["DATA_ENCRYPTION_KEY"] not in output
    with pytest.raises(RuntimeError):mod.main(["--output",str(target)])



def test_formal_database_password_cannot_be_reused_under_new_role(cfg):
    from sqlalchemy.engine import make_url
    cfg.values["DATABASE_URL"]=make_url(cfg.values["DATABASE_URL"]).set(password="production-db-unit-only").render_as_string(hide_password=False)
    cfg.save()
    with pytest.raises(RuntimeError,match="SHARED_DATABASE_PASSWORD"):
        get_settings()



def test_future_api_child_has_only_uat_profile_and_disables_callback_access_log(cfg,monkeypatch):
    path=Path(__file__).resolve().parents[1]/"scripts/run_uat.py"
    spec=importlib.util.spec_from_file_location("uat_child_runner",path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    from app import uat_preflight
    monkeypatch.setattr(uat_preflight,"check_database",lambda s:None)
    monkeypatch.setenv("DATABASE_URL","must-not-be-inherited")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN","must-not-be-inherited")
    monkeypatch.setenv("JIAAN_VAPID_PRIVATE_KEY","must-not-be-inherited")
    class Socket:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def connect_ex(self,address):return 1
    monkeypatch.setattr(mod.socket,"socket",Socket)
    monkeypatch.setattr(mod.os,"chdir",Mock())
    execute=Mock();monkeypatch.setattr(mod.os,"execve",execute)
    assert mod.main(["--kind","api","--env-file",str(cfg.path),"--launch"])==0
    command,env=execute.call_args.args[1:]
    assert command[command.index("--port")+1]=="8151" and "--no-access-log" in command
    assert env["LTC_PROFILE"]=="uat" and env["JIAAN_WEBPUSH_DISPATCH"]=="off"
    assert not ({"DATABASE_URL","LINE_CHANNEL_ACCESS_TOKEN","JIAAN_VAPID_PRIVATE_KEY"}&set(env))


@pytest.mark.parametrize("url",["https://production.test/liff","http://127.0.0.1:8151/liff","https://liff.line.me/production-liff-id","https://uat.test.evil/api/path"])
def test_old_notification_links_cannot_redirect_testers_to_formal_site(cfg,monkeypatch,url):
    cfg.values["UAT_OUTBOUND_MODE"]="allowlist";cfg.save()
    from app.line.client import RealLineClient
    send=Mock();monkeypatch.setattr(httpx,"post",send)
    result=RealLineClient(get_settings().line_channel_access_token).push(USER,[{"type":"text","text":"Open "+url}],"unit-retry")
    assert not result.accepted
    send.assert_not_called()


def test_uat_notification_link_and_current_uat_liff_link_are_allowed(cfg):
    s=get_settings()
    assert uat.messages_allowed(s,[{"type":"text","text":"Open https://uat.test/liff/cases/unit"}])
    assert uat.messages_allowed(s,[{"type":"template","template":{"actions":[{"uri":"https://liff.line.me/9000000001-unit"}]}}])



def test_production_origin_case_and_default_port_cannot_bypass_baseline(cfg):
    cfg.values["PUBLIC_BASE_URL"]="https://PRODUCTION.test:443/";cfg.save()
    with pytest.raises(RuntimeError,match="PRODUCTION_ORIGIN_FORBIDDEN"):get_settings()


def test_whitespace_cannot_disguise_reused_production_token(cfg):
    cfg.values["LINE_CHANNEL_ACCESS_TOKEN"]='"production-unit-only-line_channel_access_token "';cfg.save()
    with pytest.raises(RuntimeError,match="MISSING_OR_SHARED"):get_settings()

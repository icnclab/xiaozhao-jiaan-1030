"""Create a new private UAT file with new application keys; no production reads."""
import argparse
from pathlib import Path
import os
import secrets
from cryptography.fernet import Fernet

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True)
    args=p.parse_args(argv)
    target=Path(args.output)
    if not target.is_absolute() or not target.name.endswith(".local.env") or target.exists():
        raise RuntimeError("UAT_NEW_PRIVATE_LOCAL_ENV_PATH_REQUIRED")
    template=Path(__file__).resolve().parents[2]/"deploy/uat/uat.env.example"
    value=template.read_text(encoding="utf-8")
    for placeholder,new in {"REPLACE_NEW_RANDOM_APPLICATION_KEY":secrets.token_hex(32),"REPLACE_NEW_FERNET_KEY":Fernet.generate_key().decode(),"REPLACE_NEW_RANDOM_HEALTH_TOKEN":secrets.token_hex(32)}.items():
        value=value.replace(placeholder,new)
    target.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive create protects existing work and existing private settings.
    with target.open("x",encoding="utf-8") as f:f.write(value)
    if os.name!="nt":target.chmod(0o600)
    print("Created new private UAT file; LINE/DB placeholders still require operator input. No credentials printed.")
    return 0

if __name__=="__main__":raise SystemExit(main())

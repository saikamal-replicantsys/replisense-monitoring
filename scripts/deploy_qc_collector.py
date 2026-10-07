"""Install private QC Alloy via SSM. Never reads/logs client documents or secrets.

Preflight verifies account, instance QC tags, token metadata, application network.
Only collector files/systemd/logrotate are changed; no Terraform or application images.
Pass --execute after review. Requires boto3. Monitor the returned SSM command ID.
"""
import argparse
import base64
import json
from pathlib import Path
import boto3

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = "i-087d60682b1bd1597"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--instance", default=INSTANCE)
    args = parser.parse_args()
    session = boto3.Session(region_name="ap-south-1")
    if session.client("sts").get_caller_identity()["Account"] != "336934304897":
        raise RuntimeError("Wrong AWS account")
    instance = session.client("ec2").describe_instances(InstanceIds=[args.instance])["Reservations"][0]["Instances"][0]
    tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}
    if tags.get("Environment") != "qc" or tags.get("Name") != "replisense-qc-compute" or instance["State"]["Name"] != "running":
        raise RuntimeError("Refusing to target a non-QC/running instance")
    ssm = session.client("ssm")
    for parameter in ("GRAFANA_CLOUD_TOKEN", "OBSERVABILITY_TOKEN"):
        metadata = ssm.get_parameter(Name="/replisense/qc/" + parameter)["Parameter"]
        if metadata["Type"] != "SecureString":
            raise RuntimeError("Collector credentials must be SecureString")
    files = {}
    for name in ("config.alloy", "blackbox.yml", "compose.yaml", "credentials.py", "replisense-qc-observability.service", "logrotate.conf"):
        files[name] = base64.b64encode((ROOT / "alloy" / name).read_bytes()).decode()
    remote = """import base64,json,os,shutil,subprocess
from pathlib import Path
os.umask(0o077)
root=Path('/opt/replisense-qc-observability'); root.mkdir(mode=0o700,exist_ok=True)
subprocess.run(['docker','network','inspect','replisense-qc_application'],check=True,stdout=subprocess.DEVNULL)
for name,body in json.loads(PAYLOAD).items():
 path=root/name
 if path.exists(): shutil.copy2(path,root/(name+'.previous'))
 path.write_bytes(base64.b64decode(body))
shutil.copy2(root/'replisense-qc-observability.service','/etc/systemd/system/replisense-qc-observability.service')
shutil.copy2(root/'logrotate.conf','/etc/logrotate.d/replisense-qc-ops')
subprocess.run(['python3',str(root/'credentials.py')],check=True)
subprocess.run(['docker','compose','-f',str(root/'compose.yaml'),'pull'],check=True)
# The image seeds this named volume as alloy:alloy; the hardened collector uses
# root for 0600 credentials but has no DAC override capability. Initialize only
# its own volume ownership, using an offline helper without host/secret mounts.
image='grafana/alloy:v1.20.1@sha256:2aa2099af76c0098d4af7a4d6e48f86cb66dc1a000222ad927a1c67c6542d13f'
volume='replisense-qc-observability_alloy-data'
subprocess.run(['docker','volume','create',volume],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['docker','run','--rm','--network','none','--user','0:0',
 '--cap-drop','ALL','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE',
 '--security-opt','no-new-privileges:true','--mount','type=volume,source='+volume+',target=/var/lib/alloy',
 '--entrypoint','/bin/sh',image,'-c','chown -R 0:0 /var/lib/alloy'],check=True)
subprocess.run(['docker','compose','-f',str(root/'compose.yaml'),'run','--rm','--no-deps','alloy','validate','/etc/alloy/config.alloy'],check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','replisense-qc-observability'],check=True)
subprocess.run(['systemctl','restart','replisense-qc-observability'],check=True)
subprocess.run(['docker','compose','-f',str(root/'compose.yaml'),'ps'],check=True)
print('QC collector installed. Verify Grafana metric/log arrival and alerts separately.')
""".replace("PAYLOAD", repr(json.dumps(files)))
    encoded = base64.b64encode(remote.encode()).decode()
    command = "python3 -c \"import base64;exec(base64.b64decode('" + encoded + "'))\""
    if not args.execute:
        print("Validated QC target and SecureString metadata; would install private Alloy collector.")
        return
    response = ssm.send_command(InstanceIds=[args.instance], DocumentName="AWS-RunShellScript",
                                Parameters={"commands": [command], "executionTimeout": ["600"]}, Comment="RepliSense QC sanitized telemetry collector")
    print("SSM collector deployment command:", response["Command"]["CommandId"])


if __name__ == "__main__":
    main()

"""QC-only agent configuration repair: keep the single memory metric and rotate safe logs.

Does not change AWS alarms/IAM/networking or apply Terraform. Validates account
and QC tags; backs up current host config. Requires boto3 and --execute.
"""
import argparse
import base64
from pathlib import Path
import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    session = boto3.Session(region_name="ap-south-1")
    if session.client("sts").get_caller_identity()["Account"] != "336934304897":
        raise RuntimeError("Wrong AWS account")
    instance = "i-087d60682b1bd1597"
    data = session.client("ec2").describe_instances(InstanceIds=[instance])["Reservations"][0]["Instances"][0]
    tags = {item["Key"]: item["Value"] for item in data.get("Tags", [])}
    if tags.get("Environment") != "qc" or tags.get("Name") != "replisense-qc-compute":
        raise RuntimeError("Not isolated QC compute")
    logrotate = base64.b64encode((Path(__file__).resolve().parents[1] / "alloy/logrotate.conf").read_bytes()).decode()
    remote = """import base64,json,shutil,subprocess
from pathlib import Path
p=Path('/opt/replisense-qc/cloudwatch.json')
config=json.loads(p.read_text()); mem=config['metrics']['metrics_collected']['mem']
if 'drop_original_metrics' in mem:
 backup=p.with_name('cloudwatch.before-memory-repair.json')
 if not backup.exists(): shutil.copy2(p,backup)
 mem.pop('drop_original_metrics');p.write_text(json.dumps(config,indent=2)+'\\n')
 subprocess.run(['/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl','-a','fetch-config','-m','ec2','-c','file:'+str(p),'-s'],check=True)
Path('/etc/logrotate.d/replisense-qc-ops').write_bytes(base64.b64decode(LOGROTATE))
subprocess.run(['logrotate','--debug','/etc/logrotate.d/replisense-qc-ops'],check=True)
print('QC memory metric retained and safe operational log rotation configured.')
""".replace("LOGROTATE", repr(logrotate))
    if not args.execute:
        print("Would remove memory metric drop setting and install QC operational log rotation.")
        return
    encoded = base64.b64encode(remote.encode()).decode()
    command = "python3 -c \"import base64;exec(base64.b64decode('" + encoded + "'))\""
    response = session.client("ssm").send_command(InstanceIds=[instance], DocumentName="AWS-RunShellScript", Parameters={"commands": [command]}, Comment="Repair existing QC memory collection and rotate safe logs")
    print("SSM QC host monitoring repair:", response["Command"]["CommandId"])


if __name__ == "__main__":
    main()

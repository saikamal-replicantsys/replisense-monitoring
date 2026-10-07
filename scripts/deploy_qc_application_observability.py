"""QC-only rollout of reviewed runtime files and immutable instrumentation images.

No Terraform apply. No frontend/doc-engine change. Refuses deployment while QC
jobs are running. Saves previous runtime files and uses existing image rollback.
Requires boto3; defaults to a read-only/preparation check unless --execute is set.
"""
import argparse
import base64
import json
from pathlib import Path
import re
import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-sha", required=True)
    parser.add_argument("--python-sha", required=True)
    parser.add_argument("--instance", default="i-087d60682b1bd1597")
    parser.add_argument("--terraform-repo", type=Path, default=Path(__file__).resolve().parents[2] / "terraform-infrastructure")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not all(re.fullmatch("[a-f0-9]{40}", value) for value in (args.node_sha, args.python_sha)):
        raise RuntimeError("Full immutable commit SHA tags required")
    session = boto3.Session(region_name="ap-south-1")
    if session.client("sts").get_caller_identity()["Account"] != "336934304897":
        raise RuntimeError("Wrong AWS account")
    instance = session.client("ec2").describe_instances(InstanceIds=[args.instance])["Reservations"][0]["Instances"][0]
    tags = {item["Key"]: item["Value"] for item in instance.get("Tags", [])}
    if tags.get("Environment") != "qc" or tags.get("Name") != "replisense-qc-compute":
        raise RuntimeError("Not the isolated QC instance")
    ssm = session.client("ssm")
    saved = json.loads(ssm.get_parameter(Name="/replisense/qc/RELEASE")["Parameter"]["Value"])["release"]
    document_image = next(line.split("=", 1)[1] for line in saved.splitlines() if line.startswith("DOCUMENT_IMAGE="))
    document_sha = document_image.rsplit(":", 1)[1]
    if not re.fullmatch("[a-f0-9]{40}", document_sha):
        raise RuntimeError("Existing document-engine is not an immutable SHA")
    repositories = session.client("ecr")
    for name, sha in (("node-backend", args.node_sha), ("python-gateway", args.python_sha)):
        repositories.describe_images(repositoryName="replisense-qc/" + name, imageIds=[{"imageTag": sha}])
    files = {name: base64.b64encode((args.terraform_repo / "envs/qc/runtime" / name).read_bytes()).decode()
             for name in ("deploy.py", "compose.yaml")}
    remote = """import base64,json,shutil,subprocess,time
from pathlib import Path
root=Path('/opt/replisense-qc')
config=json.loads((root/'configuration.json').read_text())
if config.get('domain')!='qc.replicantsys.com': raise RuntimeError('Not QC configuration')
compose=['docker','compose','--env-file',str(root/'release.env'),'-f',str(root/'compose.yaml')]
probe="const mongoose=require('mongoose');(async()=>{await mongoose.connect(process.env.MONGO_URI);const Run=require('./models/qcRun');const n=await Run.countDocuments({status:'running'});console.log(JSON.stringify({running:n}));await mongoose.disconnect();process.exit(n?2:0)})().catch(()=>{console.error('QC running-job preflight failed');process.exit(3)})"
subprocess.run([*compose,'exec','-T','node-api','node','-e',probe],check=True)
backup=root/('observability-rollback-'+str(int(time.time())));backup.mkdir(mode=0o700)
for name,body in json.loads(PAYLOAD).items():
 shutil.copy2(root/name,backup/name)
 (root/name).write_bytes(base64.b64decode(body))
try:
 subprocess.run(['python3',str(root/'deploy.py'),NODE_SHA,PYTHON_SHA,DOCUMENT_SHA],check=True)
except Exception:
 for name in ('deploy.py','compose.yaml'): shutil.copy2(backup/name,root/name)
 subprocess.run([*compose,'up','-d','--wait','--wait-timeout','240'],check=True)
 raise
print('QC application instrumentation rollout complete; previous runtime files at '+str(backup))
""".replace("PAYLOAD", repr(json.dumps(files))).replace("NODE_SHA", repr(args.node_sha)).replace("PYTHON_SHA", repr(args.python_sha)).replace("DOCUMENT_SHA", repr(document_sha))
    encoded = base64.b64encode(remote.encode()).decode()
    command = "python3 -c \"import base64;exec(base64.b64decode('" + encoded + "'))\""
    if not args.execute:
        print("QC target and immutable ECR images verified; document-engine image preserved.")
        return
    response = ssm.send_command(InstanceIds=[args.instance], DocumentName="AWS-RunShellScript", Parameters={"commands": [command], "executionTimeout": ["1200"]}, Comment="QC operational instrumentation rollout")
    print("SSM application rollout command:", response["Command"]["CommandId"])


if __name__ == "__main__":
    main()

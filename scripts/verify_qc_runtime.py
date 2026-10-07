"""Read-only private QC telemetry checks via SSM; never prints credential values."""
import base64
import boto3


def main():
    session = boto3.Session(region_name="ap-south-1")
    if session.client("sts").get_caller_identity()["Account"] != "336934304897":
        raise RuntimeError("Wrong AWS account")
    instance = "i-087d60682b1bd1597"
    info = session.client("ec2").describe_instances(InstanceIds=[instance])["Reservations"][0]["Instances"][0]
    if {item["Key"]: item["Value"] for item in info.get("Tags", [])}.get("Environment") != "qc":
        raise RuntimeError("Not QC")
    probe = """(async()=>{
const token=process.env.OBSERVABILITY_TOKEN;
for(const [name,url,authenticated] of [
['node-metrics','http://node-api:5000/metrics',true],
['worker-metrics','http://qc-worker:9102/metrics',true],
['node-readiness','http://node-api:5000/ready',true],
['python-metrics','http://python-gateway:8002/metrics',false],
['document-engine-health','http://doc-engine:7001/health',false],
['node-metrics-no-token','http://node-api:5000/metrics',false],
['worker-metrics-no-token','http://qc-worker:9102/metrics',false]]){
const r=await fetch(url,{headers:authenticated?{authorization:'Bearer '+token}:{},signal:AbortSignal.timeout(10000)});
const body=await r.text();const summary={check:name,status:r.status};
if(name==='node-readiness') Object.assign(summary,JSON.parse(body));
if(name==='worker-metrics'){
 const beat=body.match(/replisense_worker_heartbeat_timestamp_seconds\\{worker="qc-worker"\\} ([0-9.]+)/);
 summary.heartbeat_age_seconds=beat?Math.round(Date.now()/1000-Number(beat[1])):null;
}
if(name==='python-metrics')summary.llm_metrics_present=body.includes('replisense_llm_requests_total');
console.log(JSON.stringify(summary));
if(r.status!==(name.endsWith('no-token')?403:200))process.exitCode=1;
}
})().catch(()=>{console.error('Private QC telemetry check failed');process.exitCode=1})"""
    encoded = base64.b64encode(probe.encode()).decode()
    command = "docker exec replisense-qc-node-api-1 node -e \"eval(Buffer.from('" + encoded + "','base64').toString())\""
    response = session.client("ssm").send_command(InstanceIds=[instance], DocumentName="AWS-RunShellScript", Parameters={"commands": [command, "docker ps --format '{{.Names}} {{.Status}} {{.Ports}}'"]}, Comment="Read-only QC instrumentation verification")
    print("SSM private QC verification command:", response["Command"]["CommandId"])


if __name__ == "__main__":
    main()

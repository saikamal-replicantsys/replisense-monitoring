"""Create private metrics credential once. Values never leave AWS SDK memory.

Requires boto3 and an authorized AWS profile. Does not overwrite existing secrets.
The Cloud Access Policy ingestion token must be supplied separately through SSM.
"""
import argparse
import secrets
import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    session = boto3.Session(region_name="ap-south-1")
    if session.client("sts").get_caller_identity()["Account"] != "336934304897":
        raise RuntimeError("Wrong AWS account")
    ssm = session.client("ssm")
    name = "/replisense/qc/OBSERVABILITY_TOKEN"
    try:
        parameter = ssm.get_parameter(Name=name)["Parameter"]
        if parameter["Type"] != "SecureString":
            raise RuntimeError("Existing metric credential is not a SecureString")
        print("QC metrics SecureString already exists; preserved unchanged.")
    except ssm.exceptions.ParameterNotFound:
        if not args.execute:
            print("Would create QC metrics SecureString. Pass --execute to create.")
            return
        ssm.put_parameter(Name=name, Type="SecureString", Value=secrets.token_urlsafe(48),
                          Tags=[{"Key": "Environment", "Value": "qc"}, {"Key": "CostCenter", "Value": "QC"}])
        print("QC metrics SecureString created successfully. Value is not displayed.")


if __name__ == "__main__":
    main()

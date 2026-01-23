from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
import json
import os

app = FastAPI(title="UnifiedBISchema - QS Connector")


# ---------- Models ----------

class AWSConnectRequest(BaseModel):
    aws_account_id: str
    region: str
    role_arn: str


# ---------- AWS Helper ----------

def assume_role(region: str, role_arn: str):
    sts = boto3.client("sts", region_name=region)

    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName="UnifiedBISchemaSession"
    )

    return {
        "aws_access_key_id": response["Credentials"]["AccessKeyId"],
        "aws_secret_access_key": response["Credentials"]["SecretAccessKey"],
        "aws_session_token": response["Credentials"]["SessionToken"],
    }


# ---------- Health ----------

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "UnifiedBISchema",
        "step": "FastAPI setup successful"
    }


# ---------- AWS Connect (Validation Only) ----------

@app.post("/aws/connect")
def connect_aws(payload: AWSConnectRequest):
    try:
        # Validate access by assuming role
        assume_role(payload.region, payload.role_arn)

        return {
            "status": "connected",
            "aws_account_id": payload.aws_account_id,
            "assumed_role": payload.role_arn
        }

    except ClientError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "AssumeRole failed",
                "message": e.response["Error"]["Message"]
            }
        )
    
@app.get("/quicksight/dashboards")
def list_quicksight_dashboards(
    aws_account_id: str,
    region: str,
    role_arn: str
):
    try:
        # Assume role
        creds = assume_role(region, role_arn)

        # Create QuickSight client with temporary creds
        qs = boto3.client(
            "quicksight",
            region_name=region,
            aws_access_key_id=creds["aws_access_key_id"],
            aws_secret_access_key=creds["aws_secret_access_key"],
            aws_session_token=creds["aws_session_token"],
        )

        # List dashboards
        response = qs.list_dashboards(
            AwsAccountId=aws_account_id
        )

        return {
            "count": len(response.get("DashboardSummaryList", [])),
            "dashboards": response.get("DashboardSummaryList", [])
        }

    except ClientError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Failed to list QuickSight dashboards",
                "message": e.response["Error"]["Message"]
            }
        )

class ExtractDashboardRequest(BaseModel):
    aws_account_id: str
    region: str
    role_arn: str
    dashboard_id: str


@app.post("/quicksight/extract-dashboard")
def extract_dashboard(payload: ExtractDashboardRequest):
    try:
        # Assume role
        creds = assume_role(payload.region, payload.role_arn)

        # Create QuickSight client
        qs = boto3.client(
            "quicksight",
            region_name=payload.region,
            aws_access_key_id=creds["aws_access_key_id"],
            aws_secret_access_key=creds["aws_secret_access_key"],
            aws_session_token=creds["aws_session_token"],
        )

        # Extract dashboard definition
        response = qs.describe_dashboard_definition(
            AwsAccountId=payload.aws_account_id,
            DashboardId=payload.dashboard_id
        )

        # Ensure storage directory exists
        os.makedirs("extracted_dashboards", exist_ok=True)

        file_path = f"extracted_dashboards/{payload.dashboard_id}.qs.json"

        # Store outside AWS
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(response, f, indent=2, default=str)

        return {
            "status": "extracted",
            "dashboard_id": payload.dashboard_id,
            "file_path": file_path
        }

    except ClientError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Failed to extract dashboard metadata",
                "message": e.response["Error"]["Message"]
            }
        )

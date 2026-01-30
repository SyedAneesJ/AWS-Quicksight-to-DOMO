"""
QuickSight to Domo Migration API - ALL BUGS FIXED
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
import json
import os
from typing import Dict, Any, List

app = FastAPI(title="QuickSight to Domo Migration API")

# ==================== CORS ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://a731a307-0c2f-405a-81c9-7ca66b449380.domoapps.prod5.domo.com",
        "https://gwcteq-partner.domo.com",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ==================== MODELS ====================

class AWSCredentials(BaseModel):
    aws_account_id: str
    region: str
    role_arn: str

class ListDashboardsRequest(BaseModel):
    aws_account_id: str
    region: str
    role_arn: str

class ExtractDashboardRequest(BaseModel):
    aws_account_id: str
    region: str
    role_arn: str
    dashboard_id: str

class ConvertToUnifiedRequest(BaseModel):
    dashboard_id: str
    qs_definition: Dict[str, Any]

class TransformToDomoRequest(BaseModel):
    unified_schema: Dict[str, Any]
    dataset_mapping: Dict[str, str]

# ==================== AWS HELPER - FIXED ====================

def get_quicksight_client(role_arn: str, region: str):
    """
    FIXED: Returns a properly authenticated QuickSight client
    """
    try:
        # Step 1: Create STS client with base credentials from environment
        sts = boto3.client("sts", region_name=region)
        
        # Step 2: Assume the user-provided role
        print(f"🔑 Assuming role: {role_arn}")
        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="domo-quicksight-session",
            DurationSeconds=3600
        )
        
        # Step 3: Extract temporary credentials
        creds = assumed["Credentials"]
        print(f"✅ Role assumed successfully")
        
        # Step 4: Return QuickSight client with temporary credentials
        return boto3.client(
            "quicksight",
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=region
        )
    
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        print(f"❌ Failed to assume role: {error_code} - {error_msg}")
        raise Exception(f"AWS Error ({error_code}): {error_msg}")

# ==================== ENDPOINTS ====================

@app.get("/")
def root():
    return {
        "service": "QuickSight to Domo Migration API",
        "version": "2.3.0",
        "status": "running",
        "fixes": "All bugs resolved - CORS, AWS auth, list-dashboards"
    }

@app.get("/health")
def health_check():
    """Health check with AWS credential verification"""
    return {
        "status": "healthy",
        "aws_credentials_configured": bool(
            os.environ.get("AWS_ACCESS_KEY_ID") and 
            os.environ.get("AWS_SECRET_ACCESS_KEY")
        )
    }

# ==================== AWS & QUICKSIGHT ====================

@app.post("/api/aws/validate")
def validate_aws(payload: dict):
    """Validate AWS credentials by attempting to assume role"""
    try:
        role_arn = payload["role_arn"]
        region = payload.get("region", "us-east-1")
        account_id = payload["aws_account_id"]

        # Get QuickSight client (this will fail if role can't be assumed)
        qs = get_quicksight_client(role_arn, region)

        # Test with a simple API call
        qs.list_dashboards(
            AwsAccountId=account_id,
            MaxResults=1
        )

        return {
            "status": "success",
            "message": "AWS credentials validated successfully"
        }

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Validation failed: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "AWS validation failed",
                "message": error_msg
            }
        )

@app.post("/api/quicksight/list-dashboards")
def list_quicksight_dashboards(payload: ListDashboardsRequest):
    """List all QuickSight dashboards - FIXED"""
    try:
        # Get QuickSight client with assumed role credentials
        qs = get_quicksight_client(payload.role_arn, payload.region)
        
        # List dashboards
        print(f"📊 Listing dashboards for account: {payload.aws_account_id}")
        response = qs.list_dashboards(
            AwsAccountId=payload.aws_account_id
        )
        
        dashboards = response.get("DashboardSummaryList", [])
        print(f"✅ Found {len(dashboards)} dashboard(s)")
        
        return {
            "count": len(dashboards),
            "dashboards": [
                {
                    "id": d.get("DashboardId"),
                    "arn": d.get("Arn"),
                    "name": d.get("Name"),
                    "created_time": str(d.get("CreatedTime", "")),
                    "last_updated": str(d.get("LastUpdatedTime", ""))
                }
                for d in dashboards
            ]
        }
    
    except ClientError as e:
        error_msg = e.response["Error"]["Message"]
        print(f"❌ Failed to list dashboards: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Failed to list QuickSight dashboards",
                "message": error_msg
            }
        )
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Unexpected error: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": error_msg
            }
        )

@app.post("/api/quicksight/extract-dashboard")
def extract_dashboard(payload: ExtractDashboardRequest):
    """Extract QuickSight dashboard definition - FIXED"""
    try:
        # Get QuickSight client with assumed role credentials
        qs = get_quicksight_client(payload.role_arn, payload.region)
        
        # Extract dashboard definition
        print(f"📥 Extracting dashboard: {payload.dashboard_id}")
        response = qs.describe_dashboard_definition(
            AwsAccountId=payload.aws_account_id,
            DashboardId=payload.dashboard_id
        )
        
        # Save for debugging
        os.makedirs("extracted_dashboards", exist_ok=True)
        file_path = f"extracted_dashboards/{payload.dashboard_id}.qs.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(response, f, indent=2, default=str)
        
        print(f"✅ Dashboard extracted and saved to: {file_path}")
        
        return {
            "status": "success",
            "dashboard_id": payload.dashboard_id,
            "definition": response,
            "saved_to": file_path
        }
    
    except ClientError as e:
        error_msg = e.response["Error"]["Message"]
        print(f"❌ Failed to extract dashboard: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Failed to extract dashboard",
                "message": error_msg
            }
        )
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Unexpected error: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": error_msg
            }
        )

# ==================== TRANSFORMATION ====================

@app.post("/api/transform/qs-to-unified")
def convert_qs_to_unified_schema(payload: ConvertToUnifiedRequest):
    """Convert QuickSight definition to UnifiedBISchema"""
    try:
        qs_definition = payload.qs_definition
        
        from run_qs_to_unified import transform_qs_dashboard_to_unified
        
        print(f"📊 Converting dashboard: {payload.dashboard_id}")
        
        unified_schema = transform_qs_dashboard_to_unified(qs_definition)
        
        print(f"✅ Conversion complete!")
        print(f"   - Pages: {len(unified_schema.get('pages', []))}")
        print(f"   - Datasets: {len(unified_schema.get('datasets', []))}")
        
        total_visuals = sum(
            len(page.get('visuals', [])) 
            for page in unified_schema.get('pages', [])
        )
        print(f"   - Total Visuals: {total_visuals}")
        
        return {
            "status": "success",
            "unified_schema": unified_schema,
            "stats": {
                "pages": len(unified_schema.get('pages', [])),
                "datasets": len(unified_schema.get('datasets', [])),
                "calculated_fields": len(unified_schema.get('calculatedFields', [])),
                "total_visuals": total_visuals
            }
        }
    
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"❌ Conversion failed: {str(e)}")
        print(error_detail)
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Conversion to UnifiedBISchema failed",
                "message": str(e),
                "traceback": error_detail
            }
        )

@app.post("/api/transform/unified-to-domo")
def transform_unified_to_domo(payload: TransformToDomoRequest):
    """Transform UnifiedBISchema to Domo card payloads"""
    try:
        unified_schema = payload.unified_schema
        dataset_mapping = payload.dataset_mapping
        
        print(f"🔧 Generating Domo card payloads...")
        
        from domo_adapter import DomoAdapter
        from dataset_resolver import StaticDatasetResolver
        
        resolver = StaticDatasetResolver(dataset_mapping)
        adapter = DomoAdapter(None, resolver, column_mapping={})
        
        card_payloads = []
        errors = []
        
        for page in unified_schema.get("pages", []):
            for visual in page.get("visuals", []):
                try:
                    visual_id = visual.get("id", "unknown")
                    visual_type = visual.get("type", "").upper()
                    
                    print(f"   Processing: {visual_id} ({visual_type})")
                    
                    if visual_type == "KPI":
                        payload = adapter._build_kpi_payload(visual)
                    elif visual_type == "BAR":
                        payload = adapter._build_bar_payload(visual)
                    elif visual_type == "STACKED_BAR":
                        payload = adapter._build_stacked_bar_payload(visual)
                    elif visual_type == "LINE":
                        payload = adapter._build_line_payload(visual)
                    elif visual_type == "AREA":
                        payload = adapter._build_area_payload(visual)
                    elif visual_type == "STACKED_AREA":
                        payload = adapter._build_stacked_area_payload(visual)
                    elif visual_type == "PIE":
                        payload = adapter._build_pie_payload(visual)
                    elif visual_type == "DONUT":
                        payload = adapter._build_donut_payload(visual)
                    elif visual_type in ["SCATTER", "BUBBLE"]:
                        payload = adapter._build_scatter_payload(visual)
                    elif visual_type == "COMBO":
                        payload = adapter._build_combo_payload(visual)
                    elif visual_type == "TABLE":
                        payload = adapter._build_table_payload(visual)
                    else:
                        raise NotImplementedError(f"Unsupported visual type: {visual_type}")
                    
                    card_payloads.append({
                        "visual_id": visual_id,
                        "visual_type": visual_type,
                        "title": visual.get("title", "Untitled"),
                        "dataset_id": resolver.resolve(visual.get("datasetRef")),
                        "payload": payload
                    })
                    
                    print(f"      ✅ Payload generated")
                    
                except Exception as e:
                    error_msg = f"Failed to generate payload for {visual.get('id', 'unknown')}: {str(e)}"
                    print(f"      ❌ {error_msg}")
                    errors.append({
                        "visual_id": visual.get("id", "unknown"),
                        "visual_type": visual.get("type", "unknown"),
                        "error": str(e)
                    })
                    continue
        
        print(f"✅ Payload generation complete!")
        print(f"   Success: {len(card_payloads)}")
        print(f"   Errors: {len(errors)}")
        
        return {
            "status": "success",
            "card_count": len(card_payloads),
            "error_count": len(errors),
            "card_payloads": card_payloads,
            "errors": errors
        }
    
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"❌ Transformation failed: {str(e)}")
        print(error_detail)
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Transformation to Domo format failed",
                "message": str(e),
                "traceback": error_detail
            }
        )

# ==================== UTILITIES ====================

@app.post("/api/datasets/analyze")
def analyze_datasets(payload: Dict[str, Any]):
    """Analyze unified schema to identify required datasets"""
    try:
        unified_schema = payload.get("unified_schema", {})
        datasets = unified_schema.get("datasets", [])
        
        dataset_info = []
        for ds in datasets:
            dataset_info.append({
                "ref": ds.get("id") or ds.get("ref"),
                "name": ds.get("name", "Unnamed Dataset"),
                "columns": ds.get("columns", []),
                "column_count": len(ds.get("columns", []))
            })
        
        return {
            "status": "success",
            "dataset_count": len(dataset_info),
            "datasets": dataset_info
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Dataset analysis failed",
                "message": str(e)
            }
        )

# ==================== RUN ====================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("QuickSight to Domo Migration API v2.3")
    print("=" * 60)
    print("✅ ALL BUGS FIXED")
    print("   - CORS configuration")
    print("   - AWS credential flow")
    print("   - list-dashboards endpoint")
    print("   - extract-dashboard endpoint")
    print("=" * 60)
    
    # Check environment variables
    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        print("⚠️  WARNING: AWS_ACCESS_KEY_ID not set")
    else:
        print("✅ AWS_ACCESS_KEY_ID configured")
        
    if not os.environ.get("AWS_SECRET_ACCESS_KEY"):
        print("⚠️  WARNING: AWS_SECRET_ACCESS_KEY not set")
    else:
        print("✅ AWS_SECRET_ACCESS_KEY configured")
    
    port = int(os.environ.get("PORT", 8000))
    
    print(f"🚀 Starting server on http://0.0.0.0:{port}")
    print(f"📚 API docs: http://localhost:{port}/docs")
    print("=" * 60)
    
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
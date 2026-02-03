"""
QuickSight to Domo Migration API - COMPLETE & WORKING
✅ Uses working run_qs_to_unified.py conversion logic
✅ Enhanced debugging for unified schema conversion
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
import json
import os
from typing import Dict, Any, List, Optional

# ✅ IMPORT THE WORKING CONVERSION FUNCTION
from run_qs_to_unified import transform_qs_dashboard_to_unified

app = FastAPI(title="QuickSight to Domo Migration API")

# ==================== CORS ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"https://.*\.domoapps\.prod.*\.domo\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

class ListDataSetsRequest(BaseModel):
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

class AnalyzeDatasetsRequest(BaseModel):
    unified_schema: Dict[str, Any]

# ==================== AWS HELPER ====================

def get_quicksight_client(role_arn: str, region: str):
    """
    Returns a properly authenticated QuickSight client
    """
    try:
        # Create STS client
        sts = boto3.client("sts", region_name=region)
        
        # Assume the role
        print(f"🔑 Assuming role: {role_arn}")
        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="domo-quicksight-session",
            DurationSeconds=3600
        )
        
        # Extract credentials
        creds = assumed["Credentials"]
        print(f"✅ Role assumed successfully")
        
        # Return QuickSight client with temporary credentials
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
        "version": "3.1.0",
        "status": "running",
        "features": [
            "AWS credential validation",
            "Dashboard listing",
            "Dataset listing with details",
            "Dashboard extraction",
            "✅ Working unified schema conversion (uses run_qs_to_unified.py)",
            "Dataset mapping support",
            "Domo transformation"
        ]
    }

@app.get("/health")
def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "aws_credentials_configured": bool(
            os.environ.get("AWS_ACCESS_KEY_ID") and 
            os.environ.get("AWS_SECRET_ACCESS_KEY")
        ),
        "conversion_module_loaded": "transform_qs_dashboard_to_unified" in dir()
    }

# ==================== AWS VALIDATION ====================

@app.post("/api/aws/validate")
def validate_aws(payload: dict):
    """Validate AWS credentials by attempting to assume role"""
    try:
        print(f"\n{'='*60}")
        print(f"🔑 VALIDATING AWS CREDENTIALS")
        print(f"{'='*60}")
        
        role_arn = payload["role_arn"]
        region = payload.get("region", "us-east-1")
        account_id = payload["aws_account_id"]

        print(f"Account ID: {account_id}")
        print(f"Region: {region}")
        print(f"Role ARN: {role_arn}")

        # Get QuickSight client (this will fail if role can't be assumed)
        qs = get_quicksight_client(role_arn, region)

        # Test with a simple API call
        response = qs.list_dashboards(
            AwsAccountId=account_id,
            MaxResults=1
        )
        
        dashboard_count = len(response.get("DashboardSummaryList", []))
        
        print(f"✅ AWS credentials validated successfully")
        print(f"{'='*60}\n")

        return {
            "status": "success",
            "message": "AWS credentials validated successfully",
            "dashboard_count": dashboard_count
        }

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Validation failed: {error_msg}")
        print(f"{'='*60}\n")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "AWS validation failed",
                "message": error_msg
            }
        )

# ==================== QUICKSIGHT DASHBOARDS ====================

@app.post("/api/quicksight/list-dashboards")
def list_quicksight_dashboards(payload: ListDashboardsRequest):
    """List all QuickSight dashboards"""
    try:
        print(f"\n{'='*60}")
        print(f"📊 LISTING QUICKSIGHT DASHBOARDS")
        print(f"{'='*60}")
        
        qs = get_quicksight_client(payload.role_arn, payload.region)
        
        response = qs.list_dashboards(AwsAccountId=payload.aws_account_id)
        
        dashboards = []
        for summary in response.get("DashboardSummaryList", []):
            dashboards.append({
                "id": summary["DashboardId"],
                "arn": summary["Arn"],
                "name": summary["Name"],
                "created_time": str(summary.get("CreatedTime", "")),
                "last_updated": str(summary.get("LastUpdatedTime", ""))
            })
        
        print(f"✅ Found {len(dashboards)} dashboard(s)")
        for db in dashboards:
            print(f"   - {db['name']} (ID: {db['id']})")
        print(f"{'='*60}\n")
        
        return {
            "count": len(dashboards),
            "dashboards": dashboards
        }
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ List dashboards failed: {error_msg}")
        print(f"{'='*60}\n")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to list dashboards",
                "message": error_msg
            }
        )

# ==================== QUICKSIGHT DATASETS ====================

@app.post("/api/quicksight/list-datasets")
def list_quicksight_datasets(payload: ListDataSetsRequest):
    """List all QuickSight datasets in the account"""
    try:
        print(f"\n{'='*60}")
        print(f"📊 LISTING QUICKSIGHT DATASETS")
        print(f"{'='*60}")
        
        qs = get_quicksight_client(payload.role_arn, payload.region)
        
        # List datasets
        response = qs.list_data_sets(AwsAccountId=payload.aws_account_id)
        
        datasets = []
        for summary in response.get("DataSetSummaries", []):
            dataset_id = summary["DataSetId"]
            
            # Get detailed dataset info
            try:
                dataset_detail = qs.describe_data_set(
                    AwsAccountId=payload.aws_account_id,
                    DataSetId=dataset_id
                )
                
                dataset_info = dataset_detail.get("DataSet", {})
                
                # Extract columns
                columns = []
                physical_table_map = dataset_info.get("PhysicalTableMap", {})
                logical_table_map = dataset_info.get("LogicalTableMap", {})
                
                # Get columns from physical tables
                for table_key, table_val in physical_table_map.items():
                    if "RelationalTable" in table_val:
                        rel_table = table_val["RelationalTable"]
                        columns.extend([col.get("Name", "") for col in rel_table.get("InputColumns", [])])
                    elif "S3Source" in table_val:
                        s3_source = table_val["S3Source"]
                        columns.extend([col.get("Name", "") for col in s3_source.get("InputColumns", [])])
                    elif "CustomSql" in table_val:
                        custom_sql = table_val["CustomSql"]
                        columns.extend([col.get("Name", "") for col in custom_sql.get("InputColumns", [])])
                
                # Extract calculated fields
                calculated_fields = []
                for calc_field in dataset_info.get("CalculatedFields", []):
                    calculated_fields.append(calc_field.get("Name", ""))
                
                # Also check logical table for additional calculated fields
                for table_key, table_val in logical_table_map.items():
                    data_transforms = table_val.get("DataTransforms", [])
                    for transform in data_transforms:
                        if "CreateColumnsOperation" in transform:
                            calc_cols = transform["CreateColumnsOperation"].get("Columns", [])
                            for col in calc_cols:
                                col_name = col.get("ColumnName", "")
                                if col_name and col_name not in calculated_fields:
                                    calculated_fields.append(col_name)
                
                datasets.append({
                    "id": dataset_id,
                    "name": summary["Name"],
                    "arn": summary["Arn"],
                    "created_time": str(summary.get("CreatedTime", "")),
                    "last_updated": str(summary.get("LastUpdatedTime", "")),
                    "import_mode": summary.get("ImportMode", "UNKNOWN"),
                    "columns": columns,
                    "calculated_fields": calculated_fields,
                    "column_count": len(columns),
                    "calculated_field_count": len(calculated_fields)
                })
                
                print(f"   - {summary['Name']}: {len(columns)} columns, {len(calculated_fields)} calc fields")
            
            except Exception as detail_error:
                print(f"⚠️ Could not get details for dataset {dataset_id}: {detail_error}")
                # Add basic info even if details fail
                datasets.append({
                    "id": dataset_id,
                    "name": summary["Name"],
                    "arn": summary["Arn"],
                    "created_time": str(summary.get("CreatedTime", "")),
                    "last_updated": str(summary.get("LastUpdatedTime", "")),
                    "import_mode": summary.get("ImportMode", "UNKNOWN"),
                    "columns": [],
                    "calculated_fields": [],
                    "column_count": 0,
                    "calculated_field_count": 0
                })
        
        print(f"✅ Found {len(datasets)} dataset(s)")
        print(f"{'='*60}\n")
        
        return {
            "count": len(datasets),
            "datasets": datasets
        }
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ List datasets failed: {error_msg}")
        print(f"{'='*60}\n")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to list datasets",
                "message": error_msg
            }
        )

# ==================== DASHBOARD EXTRACTION ====================

@app.post("/api/quicksight/extract-dashboard")
def extract_dashboard(payload: ExtractDashboardRequest):
    """Extract QuickSight dashboard definition"""
    try:
        print(f"\n{'='*60}")
        print(f"📥 EXTRACTING DASHBOARD")
        print(f"{'='*60}")
        print(f"Dashboard ID: {payload.dashboard_id}")
        
        qs = get_quicksight_client(payload.role_arn, payload.region)
        
        response = qs.describe_dashboard_definition(
            AwsAccountId=payload.aws_account_id,
            DashboardId=payload.dashboard_id
        )
        
        # Save to file for debugging
        os.makedirs("extracted_dashboards", exist_ok=True)
        file_path = f"extracted_dashboards/{payload.dashboard_id}.qs.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(response, f, indent=2, default=str)
        
        print(f"✅ Dashboard extracted successfully")
        print(f"💾 Saved to: {file_path}")
        print(f"{'='*60}\n")
        
        return {
            "status": "success",
            "dashboard_id": payload.dashboard_id,
            "definition": response,
            "saved_to": file_path
        }
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Extract dashboard failed: {error_msg}")
        print(f"{'='*60}\n")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to extract dashboard",
                "message": error_msg
            }
        )

# ==================== UNIFIED SCHEMA CONVERSION (FIXED WITH DEBUGGING!) ====================

@app.post("/api/transform/qs-to-unified")
def convert_to_unified_schema(payload: ConvertToUnifiedRequest):
    """
    Convert QuickSight dashboard definition to unified schema
    
    ✅ FIXED: Properly extracts the Definition from the response
    """
    try:
        print(f"\n{'='*60}")
        print(f"🔄 CONVERTING TO UNIFIED SCHEMA")
        print(f"{'='*60}")
        print(f"Dashboard ID: {payload.dashboard_id}")
        
        # 🐛 DEBUG: Check what we received
        print(f"\n🐛 DEBUG: Input structure analysis")
        print(f"   Type: {type(payload.qs_definition)}")
        print(f"   Keys: {list(payload.qs_definition.keys())}")
        
        # ✅ CRITICAL FIX: Extract the actual QuickSight response
        # The frontend sends: { status, dashboard_id, definition }
        # But we need the AWS QuickSight response which is IN the 'definition' key
        
        if 'definition' in payload.qs_definition:
            # Frontend sent wrapped response
            print(f"   📦 Unwrapping: Found 'definition' key")
            qs_response = payload.qs_definition['definition']
        elif 'Definition' in payload.qs_definition:
            # Already the correct format
            print(f"   ✅ Direct: Already has 'Definition' key")
            qs_response = payload.qs_definition
        else:
            # Assume it's the direct response
            print(f"   ⚠️  Warning: No definition/Definition key found")
            qs_response = payload.qs_definition
        
        # Now check the structure
        print(f"\n📊 QuickSight response structure:")
        print(f"   Type: {type(qs_response)}")
        print(f"   Keys: {list(qs_response.keys())[:10]}")
        print(f"   Has 'DashboardId': {'DashboardId' in qs_response}")
        print(f"   Has 'Name': {'Name' in qs_response}")
        print(f"   Has 'Definition': {'Definition' in qs_response}")
        
        if 'Definition' in qs_response:
            definition = qs_response['Definition']
            print(f"\n📋 Definition structure:")
            print(f"   Type: {type(definition)}")
            print(f"   Keys: {list(definition.keys())[:10]}")
            print(f"   Has 'Sheets': {'Sheets' in definition}")
            print(f"   Has 'DataSetIdentifierDeclarations': {'DataSetIdentifierDeclarations' in definition}")
            
            if 'Sheets' in definition:
                sheets = definition['Sheets']
                print(f"   Sheets count: {len(sheets)}")
                if sheets:
                    print(f"   First sheet has visuals: {'Visuals' in sheets[0]}")
                    if 'Visuals' in sheets[0]:
                        print(f"   Visual count: {len(sheets[0]['Visuals'])}")
            
            if 'DataSetIdentifierDeclarations' in definition:
                datasets = definition['DataSetIdentifierDeclarations']
                print(f"   Dataset declarations: {len(datasets)}")
                for ds in datasets:
                    print(f"      - {ds.get('Identifier')} (ARN: {ds.get('DataSetArn', 'N/A')[:50]}...)")
        
        # ✅ Call the conversion function with the CORRECT format
        print(f"\n🔄 Calling transform_qs_dashboard_to_unified()...")
        unified_schema = transform_qs_dashboard_to_unified(qs_response)
        
        print(f"\n{'='*60}")
        print(f"✅ CONVERSION COMPLETE")
        print(f"{'='*60}")
        print(f"Schema Version: {unified_schema.get('schemaVersion', 'Unknown')}")
        print(f"Dashboard ID: {unified_schema.get('source', {}).get('dashboardId')}")
        print(f"Dashboard Name: {unified_schema.get('source', {}).get('dashboardName')}")
        print(f"Datasets: {len(unified_schema.get('datasets', []))}")
        print(f"Pages: {len(unified_schema.get('pages', []))}")
        
        total_visuals = sum(len(page.get('visuals', [])) for page in unified_schema.get('pages', []))
        print(f"Total Visuals: {total_visuals}")
        print(f"Calculated Fields: {len(unified_schema.get('calculatedFields', []))}")
        
        # Show dataset details
        if unified_schema.get('datasets'):
            print(f"\n📊 Dataset Details:")
            for ds in unified_schema['datasets']:
                print(f"   - {ds.get('name', 'Unknown')} (ID: {ds.get('id', 'Unknown')})")
                if 'sourceArn' in ds:
                    print(f"     ARN: {ds['sourceArn'][:60]}...")
        else:
            print(f"\n⚠️  WARNING: No datasets found!")
        
        # Show visual count by type
        visual_types = {}
        for page in unified_schema.get('pages', []):
            for visual in page.get('visuals', []):
                vtype = visual.get('type', 'Unknown')
                visual_types[vtype] = visual_types.get(vtype, 0) + 1
        
        if visual_types:
            print(f"\n📈 Visual Types:")
            for vtype, count in visual_types.items():
                print(f"   - {vtype}: {count}")
        else:
            print(f"\n⚠️  WARNING: No visuals found!")
        
        print(f"{'='*60}\n")
        
        # Save to file for debugging
        os.makedirs("unified_schemas", exist_ok=True)
        unified_file = f"unified_schemas/{payload.dashboard_id}.unified.json"
        with open(unified_file, "w", encoding="utf-8") as f:
            json.dump(unified_schema, f, indent=2)
        print(f"💾 Saved unified schema to: {unified_file}")
        
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
        print(f"\n❌ CONVERSION FAILED")
        print(f"Error: {str(e)}")
        print(f"Traceback:\n{error_detail}")
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Conversion failed",
                "message": str(e),
                "traceback": error_detail
            }
        )

# ==================== DATASET ANALYSIS ====================

@app.post("/api/datasets/analyze")
def analyze_datasets(payload: AnalyzeDatasetsRequest):
    """
    Analyze datasets from unified schema
    """
    try:
        print(f"🔍 Analyzing datasets from unified schema")
        
        unified_schema = payload.unified_schema
        datasets = unified_schema.get("datasets", [])
        
        print(f"✅ Found {len(datasets)} dataset(s) to analyze")
        
        # Format dataset info for frontend
        analyzed_datasets = []
        for ds in datasets:
            analyzed_datasets.append({
                "ref": ds.get("ref", ds.get("id", "unknown")),
                "name": ds.get("name", "Unnamed Dataset"),
                "columns": ds.get("columns", []),
                "column_count": len(ds.get("columns", [])),
                "calculated_fields": ds.get("calculatedFields", []),
                "calculated_field_count": len(ds.get("calculatedFields", []))
            })
        
        return {
            "status": "success",
            "dataset_count": len(analyzed_datasets),
            "datasets": analyzed_datasets
        }
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Dataset analysis failed: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Dataset analysis failed",
                "message": error_msg
            }
        )

# ==================== DOMO TRANSFORMATION ====================

@app.post("/api/transform/unified-to-domo")
def transform_to_domo(payload: TransformToDomoRequest):
    """
    Transform unified schema to Domo card payloads
    """
    try:
        print(f"\n{'='*60}")
        print(f"🔄 TRANSFORMING TO DOMO CARD PAYLOADS")
        print(f"{'='*60}")
        
        unified = payload.unified_schema
        dataset_mapping = payload.dataset_mapping
        
        print(f"Dataset Mapping:")
        for qs_ref, domo_id in dataset_mapping.items():
            print(f"   {qs_ref} → {domo_id}")
        
        card_payloads = []
        errors = []
        
        # Iterate through pages and visuals
        for page in unified.get("pages", []):
            print(f"\nProcessing page: {page.get('name', 'Untitled')}")
            
            for visual in page.get("visuals", []):
                try:
                    # Get dataset reference
                    dataset_ref = visual.get("datasetRef", "")
                    
                    # Map to Domo dataset ID
                    domo_dataset_id = dataset_mapping.get(dataset_ref, "")
                    
                    if not domo_dataset_id:
                        errors.append({
                            "visual_id": visual.get("id"),
                            "error": f"No dataset mapping found for: {dataset_ref}"
                        })
                        print(f"   ⚠️ Skipped {visual.get('type')}: No dataset mapping for {dataset_ref}")
                        continue
                    
                    # Create basic card payload
                    card_payload = {
                        "visual_id": visual.get("id"),
                        "visual_type": visual.get("type"),
                        "title": visual.get("title", "Untitled Visual"),
                        "dataset_id": domo_dataset_id,
                        "payload": {
                            "title": visual.get("title", "Untitled Visual"),
                            "dataSourceId": domo_dataset_id,
                            "cardType": "doc_card",
                            "description": f"Migrated from QuickSight - {visual.get('type')}"
                        }
                    }
                    
                    card_payloads.append(card_payload)
                    print(f"   ✅ Created payload for {visual.get('type')}: {visual.get('title')}")
                
                except Exception as visual_error:
                    errors.append({
                        "visual_id": visual.get("id"),
                        "error": str(visual_error)
                    })
                    print(f"   ❌ Error: {visual_error}")
        
        print(f"\n{'='*60}")
        print(f"✅ Created {len(card_payloads)} card payload(s)")
        if errors:
            print(f"⚠️ {len(errors)} error(s) occurred")
        print(f"{'='*60}\n")
        
        return {
            "status": "success",
            "card_count": len(card_payloads),
            "error_count": len(errors),
            "card_payloads": card_payloads,
            "errors": errors
        }
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Transformation failed: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Transformation to Domo failed",
                "message": error_msg
            }
        )

# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))

    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
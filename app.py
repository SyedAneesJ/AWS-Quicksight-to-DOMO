"""
QuickSight to Domo Migration API - WITH DATASET SUPPORT
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
import json
import os
from typing import Dict, Any, List, Optional

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

# ==================== DATASET EXTRACTION HELPERS ====================

def extract_datasets_from_definition(dashboard_def: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract dataset information from QuickSight dashboard definition
    """
    datasets = []
    dataset_refs = set()
    
    # Try to get datasets from DataSetIdentifierDeclarations
    data_set_declarations = dashboard_def.get("DataSetIdentifierDeclarations", [])
    
    print(f"📊 Found {len(data_set_declarations)} dataset declarations")
    
    for decl in data_set_declarations:
        dataset_ref = decl.get("Identifier", "")
        dataset_arn = decl.get("DataSetArn", "")
        
        if dataset_ref and dataset_ref not in dataset_refs:
            dataset_refs.add(dataset_ref)
            
            # Extract dataset ID from ARN
            dataset_id = dataset_arn.split("/")[-1] if dataset_arn else dataset_ref
            
            datasets.append({
                "id": dataset_id,
                "ref": dataset_ref,
                "name": dataset_ref.replace("_", " ").title(),
                "arn": dataset_arn,
                "columns": [],  # Will be populated if we fetch details
                "calculatedFields": []
            })
    
    # Also check in sheets for any additional dataset references
    sheets = dashboard_def.get("Sheets", [])
    for sheet in sheets:
        # Check visuals for dataset references
        visuals = sheet.get("Visuals", [])
        for visual in visuals:
            # Look for ChartConfiguration which contains dataset references
            chart_config = visual.get("ChartConfiguration", {})
            field_wells = chart_config.get("FieldWells", {})
            
            # Extract any dataset identifiers from field wells
            if isinstance(field_wells, dict):
                for key, value in field_wells.items():
                    if isinstance(value, dict):
                        for field_list in value.values():
                            if isinstance(field_list, list):
                                for field in field_list:
                                    if isinstance(field, dict) and "DataSetIdentifier" in field:
                                        dataset_ref = field["DataSetIdentifier"]
                                        if dataset_ref not in dataset_refs:
                                            dataset_refs.add(dataset_ref)
                                            datasets.append({
                                                "id": dataset_ref,
                                                "ref": dataset_ref,
                                                "name": dataset_ref.replace("_", " ").title(),
                                                "columns": [],
                                                "calculatedFields": []
                                            })
    
    print(f"✅ Extracted {len(datasets)} unique dataset(s)")
    return datasets

def get_dataset_details(qs_client, aws_account_id: str, dataset_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch detailed information about a specific dataset
    """
    try:
        print(f"📥 Fetching details for dataset: {dataset_id}")
        
        response = qs_client.describe_data_set(
            AwsAccountId=aws_account_id,
            DataSetId=dataset_id
        )
        
        dataset_info = response.get("DataSet", {})
        
        # Extract column information
        physical_table_map = dataset_info.get("PhysicalTableMap", {})
        logical_table_map = dataset_info.get("LogicalTableMap", {})
        
        columns = []
        calculated_fields = []
        
        # Get columns from logical table map
        for table_name, table_def in logical_table_map.items():
            source = table_def.get("Source", {})
            
            # Get physical table ID
            physical_table_id = source.get("PhysicalTableId", "")
            
            # Get columns from physical table
            if physical_table_id in physical_table_map:
                physical_table = physical_table_map[physical_table_id]
                
                # Handle different table types
                if "RelationalTable" in physical_table:
                    input_columns = physical_table["RelationalTable"].get("InputColumns", [])
                    columns.extend([col.get("Name", "") for col in input_columns])
                elif "S3Source" in physical_table:
                    input_columns = physical_table["S3Source"].get("InputColumns", [])
                    columns.extend([col.get("Name", "") for col in input_columns])
                elif "CustomSql" in physical_table:
                    input_columns = physical_table["CustomSql"].get("InputColumns", [])
                    columns.extend([col.get("Name", "") for col in input_columns])
            
            # Get calculated fields
            data_transforms = table_def.get("DataTransforms", [])
            for transform in data_transforms:
                if "CreateColumnsOperation" in transform:
                    calc_fields = transform["CreateColumnsOperation"].get("Columns", [])
                    for field in calc_fields:
                        field_name = field.get("ColumnName", "")
                        if field_name:
                            calculated_fields.append(field_name)
                            columns.append(f"{field_name} (calculated)")
        
        print(f"✅ Found {len(columns)} columns, {len(calculated_fields)} calculated fields")
        
        return {
            "id": dataset_id,
            "name": dataset_info.get("Name", dataset_id),
            "columns": columns,
            "calculatedFields": calculated_fields,
            "importMode": dataset_info.get("ImportMode", "UNKNOWN")
        }
    
    except ClientError as e:
        error_msg = e.response["Error"]["Message"]
        print(f"⚠️ Could not fetch dataset details for {dataset_id}: {error_msg}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error fetching dataset {dataset_id}: {str(e)}")
        return None

# ==================== ENDPOINTS ====================

@app.get("/")
def root():
    return {
        "service": "QuickSight to Domo Migration API",
        "version": "2.4.0",
        "status": "running",
        "features": [
            "AWS credential validation",
            "Dashboard listing",
            "Dataset listing",
            "Dashboard extraction",
            "Dataset discovery",
            "Unified schema conversion"
        ]
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
        response = qs.list_dashboards(
            AwsAccountId=account_id,
            MaxResults=1
        )
        
        dashboard_count = len(response.get("DashboardSummaryList", []))

        return {
            "status": "success",
            "message": "AWS credentials validated successfully",
            "dashboard_count": dashboard_count
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
    """List all QuickSight dashboards"""
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

@app.post("/api/quicksight/list-datasets")
def list_quicksight_datasets(payload: ListDataSetsRequest):
    """
    NEW ENDPOINT: List all QuickSight datasets
    """
    try:
        # Get QuickSight client with assumed role credentials
        qs = get_quicksight_client(payload.role_arn, payload.region)
        
        # List datasets
        print(f"📊 Listing datasets for account: {payload.aws_account_id}")
        response = qs.list_data_sets(
            AwsAccountId=payload.aws_account_id
        )
        
        datasets = response.get("DataSetSummaries", [])
        print(f"✅ Found {len(datasets)} dataset(s)")
        
        # Get detailed info for each dataset (up to first 10)
        detailed_datasets = []
        for ds_summary in datasets[:10]:  # Limit to avoid long processing
            dataset_id = ds_summary.get("DataSetId")
            dataset_name = ds_summary.get("Name")
            
            # Try to get details
            details = get_dataset_details(qs, payload.aws_account_id, dataset_id)
            
            if details:
                detailed_datasets.append({
                    "id": dataset_id,
                    "name": dataset_name,
                    "arn": ds_summary.get("Arn", ""),
                    "created_time": str(ds_summary.get("CreatedTime", "")),
                    "last_updated": str(ds_summary.get("LastUpdatedTime", "")),
                    "import_mode": details.get("importMode", "UNKNOWN"),
                    "columns": details.get("columns", []),
                    "calculated_fields": details.get("calculatedFields", []),
                    "column_count": len(details.get("columns", [])),
                    "calculated_field_count": len(details.get("calculatedFields", []))
                })
            else:
                # Add basic info if details fetch failed
                detailed_datasets.append({
                    "id": dataset_id,
                    "name": dataset_name,
                    "arn": ds_summary.get("Arn", ""),
                    "created_time": str(ds_summary.get("CreatedTime", "")),
                    "last_updated": str(ds_summary.get("LastUpdatedTime", "")),
                    "import_mode": "UNKNOWN",
                    "columns": [],
                    "calculated_fields": [],
                    "column_count": 0,
                    "calculated_field_count": 0
                })
        
        return {
            "count": len(datasets),
            "datasets": detailed_datasets
        }
    
    except ClientError as e:
        error_msg = e.response["Error"]["Message"]
        print(f"❌ Failed to list datasets: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Failed to list QuickSight datasets",
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
    """Extract QuickSight dashboard definition"""
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
def convert_to_unified_schema(payload: ConvertToUnifiedRequest):
    """
    Convert QuickSight definition to Unified Schema
    WITH DATASET EXTRACTION
    """
    try:
        print(f"🔄 Converting dashboard {payload.dashboard_id} to unified schema")
        
        qs_def = payload.qs_definition
        
        # Extract datasets from the definition
        datasets = extract_datasets_from_definition(qs_def)
        
        # Build unified schema
        unified = {
            "dashboardId": payload.dashboard_id,
            "dashboardName": qs_def.get("Name", payload.dashboard_id),
            "datasets": datasets,
            "pages": [],
            "filters": [],
            "calculatedFields": []
        }
        
        # Extract sheets/pages
        sheets = qs_def.get("Sheets", [])
        for sheet in sheets:
            page = {
                "pageId": sheet.get("SheetId", ""),
                "pageName": sheet.get("Name", "Untitled"),
                "visuals": []
            }
            
            # Extract visuals
            visuals = sheet.get("Visuals", [])
            for visual in visuals:
                visual_obj = {
                    "visualId": visual.get("VisualId", ""),
                    "visualType": list(visual.keys())[0] if visual else "Unknown",
                    "title": visual.get("Title", {}).get("FormatText", {}).get("PlainText", ""),
                    "datasetRef": ""  # Will be populated from visual data
                }
                
                # Try to extract dataset reference
                chart_config = visual.get("ChartConfiguration", {})
                field_wells = chart_config.get("FieldWells", {})
                
                # Look for DataSetIdentifier in any field
                if isinstance(field_wells, dict):
                    for category_fields in field_wells.values():
                        if isinstance(category_fields, dict):
                            for field_list in category_fields.values():
                                if isinstance(field_list, list) and len(field_list) > 0:
                                    first_field = field_list[0]
                                    if isinstance(first_field, dict) and "DataSetIdentifier" in first_field:
                                        visual_obj["datasetRef"] = first_field["DataSetIdentifier"]
                                        break
                
                page["visuals"].append(visual_obj)
            
            unified["pages"].append(page)
        
        # Save unified schema
        os.makedirs("unified_schemas", exist_ok=True)
        file_path = f"unified_schemas/{payload.dashboard_id}.unified.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(unified, f, indent=2)
        
        print(f"✅ Unified schema created:")
        print(f"   - Pages: {len(unified['pages'])}")
        print(f"   - Datasets: {len(unified['datasets'])}")
        print(f"   - Total visuals: {sum(len(p['visuals']) for p in unified['pages'])}")
        
        return {
            "status": "success",
            "unified_schema": unified,
            "stats": {
                "pages": len(unified["pages"]),
                "datasets": len(unified["datasets"]),
                "calculated_fields": len(unified["calculatedFields"]),
                "total_visuals": sum(len(p["visuals"]) for p in unified["pages"])
            }
        }
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Conversion failed: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Conversion to unified schema failed",
                "message": error_msg
            }
        )

@app.post("/api/datasets/analyze")
def analyze_datasets(payload: AnalyzeDatasetsRequest):
    """
    NEW ENDPOINT: Analyze datasets from unified schema
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

@app.post("/api/transform/unified-to-domo")
def transform_to_domo(payload: TransformToDomoRequest):
    """
    Transform unified schema to Domo card payloads
    """
    try:
        print(f"🔄 Transforming to Domo card payloads")
        
        unified = payload.unified_schema
        dataset_mapping = payload.dataset_mapping
        
        card_payloads = []
        errors = []
        
        # Iterate through pages and visuals
        for page in unified.get("pages", []):
            for visual in page.get("visuals", []):
                try:
                    # Get dataset reference
                    dataset_ref = visual.get("datasetRef", "")
                    
                    # Map to Domo dataset ID
                    domo_dataset_id = dataset_mapping.get(dataset_ref, "")
                    
                    if not domo_dataset_id:
                        errors.append({
                            "visual_id": visual.get("visualId"),
                            "error": f"No dataset mapping found for: {dataset_ref}"
                        })
                        continue
                    
                    # Create basic card payload
                    card_payload = {
                        "visual_id": visual.get("visualId"),
                        "visual_type": visual.get("visualType"),
                        "title": visual.get("title", "Untitled Visual"),
                        "dataset_id": domo_dataset_id,
                        "payload": {
                            "title": visual.get("title", "Untitled Visual"),
                            "dataSourceId": domo_dataset_id,
                            "cardType": "doc_card",  # Default type
                            "description": f"Migrated from QuickSight - {visual.get('visualType')}"
                        }
                    }
                    
                    card_payloads.append(card_payload)
                
                except Exception as visual_error:
                    errors.append({
                        "visual_id": visual.get("visualId"),
                        "error": str(visual_error)
                    })
        
        print(f"✅ Created {len(card_payloads)} card payload(s)")
        if errors:
            print(f"⚠️ {len(errors)} error(s) occurred")
        
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
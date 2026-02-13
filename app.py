"""
QuickSight to Domo Migration API - COMPLETE & WORKING
✅ Uses working run_qs_to_unified.py conversion logic
✅ Enhanced debugging for unified schema conversion
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
import json
import os
import requests
from typing import Dict, Any, List, Optional

# ✅ IMPORT THE WORKING CONVERSION FUNCTION
from run_qs_to_unified import transform_qs_dashboard_to_unified
from domo_adapter import DomoAdapter
from dataset_resolver import StaticDatasetResolver
from domo_auth import get_domo_access_token
import base64
from domo_client import DomoClient
from domo_dataset_index import search_domo_datasets, refresh_domo_dataset_index, get_domo_dataset_index_status, warm_index_async, is_warming

from datasource_inspector import DataSourceInspector, extract_datasource_metadata
from dataset_registry import DatasetRegistry

app = FastAPI(title="QuickSight to Domo Migration API")

# Dataset registry for datasource-aware mapping
dataset_registry = DatasetRegistry(storage_path="dataset_mappings.json")

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
    external_id: Optional[str] = None

class ListDashboardsRequest(BaseModel):
    aws_account_id: str
    region: str
    role_arn: str
    external_id: Optional[str] = None

class ListDataSetsRequest(BaseModel):
    aws_account_id: str
    region: str
    role_arn: str
    external_id: Optional[str] = None

class DescribeDataSetRequest(BaseModel):
    aws_account_id: str
    region: str
    role_arn: str
    external_id: Optional[str] = None
    dataset_id: Optional[str] = None
    dataset_arn: Optional[str] = None

class ExtractDashboardRequest(BaseModel):
    aws_account_id: str
    region: str
    role_arn: str
    external_id: Optional[str] = None
    dashboard_id: str

class ConvertToUnifiedRequest(BaseModel):
    dashboard_id: str
    qs_definition: Dict[str, Any]

class TransformToDomoRequest(BaseModel):
    unified_schema: Dict[str, Any]
    dataset_mapping: Dict[str, str]

class AnalyzeDatasetsRequest(BaseModel):
    unified_schema: Dict[str, Any]

class CreateDomoCardRequest(BaseModel):
    page_id: str
    title: str
    dataset_id: str
    visual_type: Optional[str] = None
    description: Optional[str] = None

class DomoDatasetDetailRequest(BaseModel):
    dataset_id: str

class DescribeDataSetWithSourceRequest(BaseModel):
    """Enhanced dataset description request that includes datasource info"""
    aws_account_id: str
    region: str
    role_arn: str
    external_id: Optional[str] = None
    dataset_id: Optional[str] = None
    dataset_arn: Optional[str] = None

class RegisterDatasetRequest(BaseModel):
    qs_dataset_id: str
    qs_dataset_name: str
    datasource_type: str
    connection_properties: Dict[str, Any]
    domo_dataset_id: Optional[str] = None

class SuggestMatchRequest(BaseModel):
    qs_dataset_id: str
    domo_datasets: List[Dict[str, Any]]



# ==================== AWS HELPER ====================

def format_datasource_display(datasource_info: dict) -> str:
    """
    Format datasource info for display in logs/UI
    
    Args:
        datasource_info: Datasource info dict
    
    Returns:
        Formatted string
    """
    ds_type = datasource_info.get('type', 'UNKNOWN')
    props = datasource_info.get('connection_properties', {})
    
    if ds_type == 'SNOWFLAKE':
        return f"Snowflake: {props.get('database')}.{props.get('schema')}.{props.get('table')}"
    elif ds_type == 'REDSHIFT':
        return f"Redshift: {props.get('database')}.{props.get('schema')}.{props.get('table')}"
    elif ds_type in ['POSTGRES', 'MYSQL', 'MARIADB']:
        return f"{ds_type}: {props.get('database')}.{props.get('table')}"
    elif ds_type == 'S3':
        return f"S3: {datasource_info.get('name', 'Unknown')}"
    elif ds_type == 'ATHENA':
        return f"Athena: {props.get('database')}.{props.get('schema')}.{props.get('table')}"
    else:
        return f"{ds_type}: {datasource_info.get('name', 'Unknown')}"
        

def get_quicksight_client(role_arn: str, region: str, external_id: Optional[str] = None):
    """
    Returns a properly authenticated QuickSight client
    """
    try:
        # Create STS client
        sts = boto3.client("sts", region_name=region)
        
        # Assume the role
        print(f"🔑 Assuming role: {role_arn}")
        assume_kwargs = {
            "RoleArn": role_arn,
            "RoleSessionName": "domo-quicksight-session",
            "DurationSeconds": 3600
        }
        if external_id:
            assume_kwargs["ExternalId"] = external_id

        assumed = sts.assume_role(**assume_kwargs)
        
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

# ==================== ENHANCED COLUMN EXTRACTION ====================

def extract_columns_from_dataset(dataset_info: Dict[str, Any]) -> tuple:
    """
    ROBUST column extraction from QuickSight datasets.
    
    Returns: (columns_list, calculated_fields_list)
    """
    columns = []
    calculated_fields = []
    
    dataset_name = dataset_info.get('Name', 'Unknown')
    print(f"\n🔍 Extracting columns from: {dataset_name}")
    
    # ===================================================================
    # METHOD 1: OutputColumns (MOST RELIABLE - ALWAYS CHECK THIS FIRST)
    # ===================================================================
    output_columns = dataset_info.get('OutputColumns', [])
    if output_columns:
        print(f"   ✅ OutputColumns found: {len(output_columns)} columns")
        for col in output_columns:
            col_name = col.get('Name')
            col_type = col.get('Type', '')
            col_description = col.get('Description', '')
            
            if not col_name:
                continue
                
            # Check if it's a calculated field
            # Calculated fields often have specific markers
            is_calculated = (
                'CALCULATED' in col_type.upper() or
                col_description.startswith('Calculated') or
                col.get('IsCalculatedField', False)
            )
            
            if is_calculated:
                calculated_fields.append(col_name)
                print(f"      📊 Calculated: {col_name} ({col_type})")
            else:
                columns.append(col_name)
                print(f"      ✓ Column: {col_name} ({col_type})")
        
        # If OutputColumns worked, we can return early
        if columns or calculated_fields:
            print(f"   ✅ SUCCESS via OutputColumns: {len(columns)} cols, {len(calculated_fields)} calc")
            return columns, calculated_fields
    else:
        print(f"   ⚠️ No OutputColumns found")
    
    # ===================================================================
    # METHOD 2: PhysicalTableMap -> InputColumns
    # ===================================================================
    print(f"   🔄 Trying PhysicalTableMap...")
    physical_table_map = dataset_info.get('PhysicalTableMap', {})
    
    if physical_table_map:
        print(f"   ✅ PhysicalTableMap found: {len(physical_table_map)} tables")
        
        for table_key, table_def in physical_table_map.items():
            print(f"      Checking table: {table_key}")
            
            # Check all possible table types
            for table_type in ['S3Source', 'RelationalTable', 'CustomSql']:
                if table_type in table_def:
                    table_source = table_def[table_type]
                    input_columns = table_source.get('InputColumns', [])
                    
                    print(f"         {table_type}: {len(input_columns)} columns")
                    
                    for col in input_columns:
                        col_name = col.get('Name')
                        if col_name and col_name not in columns:
                            columns.append(col_name)
                            print(f"            ✓ {col_name}")
        
        if columns:
            print(f"   ✅ SUCCESS via PhysicalTableMap: {len(columns)} columns")
    else:
        print(f"   ⚠️ No PhysicalTableMap found")
    
    # ===================================================================
    # METHOD 3: LogicalTableMap -> Source -> PhysicalTableId
    # ===================================================================
    if not columns:
        print(f"   🔄 Trying LogicalTableMap...")
        logical_table_map = dataset_info.get('LogicalTableMap', {})
        
        if logical_table_map:
            print(f"   ✅ LogicalTableMap found: {len(logical_table_map)} tables")
            
            for table_key, table_def in logical_table_map.items():
                print(f"      Checking logical table: {table_key}")
                
                # Get the physical table ID this logical table references
                source = table_def.get('Source', {})
                physical_table_id = source.get('PhysicalTableId')
                
                if physical_table_id and physical_table_id in physical_table_map:
                    print(f"         References physical table: {physical_table_id}")
                    physical_table = physical_table_map[physical_table_id]
                    
                    # Extract columns from the referenced physical table
                    for table_type in ['S3Source', 'RelationalTable', 'CustomSql']:
                        if table_type in physical_table:
                            input_columns = physical_table[table_type].get('InputColumns', [])
                            print(f"         {table_type}: {len(input_columns)} columns")
                            
                            for col in input_columns:
                                col_name = col.get('Name')
                                if col_name and col_name not in columns:
                                    columns.append(col_name)
        
        if columns:
            print(f"   ✅ SUCCESS via LogicalTableMap: {len(columns)} columns")
    
    # ===================================================================
    # METHOD 4: ColumnGroups
    # ===================================================================
    if not columns:
        print(f"   🔄 Trying ColumnGroups...")
        column_groups = dataset_info.get('ColumnGroups', [])
        
        if column_groups:
            print(f"   ✅ ColumnGroups found: {len(column_groups)} groups")
            
            for group in column_groups:
                geo_columns = group.get('GeoSpatialColumnGroup', {}).get('Columns', [])
                for col_name in geo_columns:
                    if col_name and col_name not in columns:
                        columns.append(col_name)
                        print(f"      ✓ GeoColumn: {col_name}")
        
        if columns:
            print(f"   ✅ SUCCESS via ColumnGroups: {len(columns)} columns")
    
    # ===================================================================
    # METHOD 5: FieldFolders (contains field names)
    # ===================================================================
    if not columns:
        print(f"   🔄 Trying FieldFolders...")
        field_folders = dataset_info.get('FieldFolders', {})
        
        if field_folders:
            print(f"   ✅ FieldFolders found: {len(field_folders)} folders")
            
            for folder_name, folder_data in field_folders.items():
                folder_columns = folder_data.get('columns', [])
                print(f"      Folder '{folder_name}': {len(folder_columns)} columns")
                
                for col_name in folder_columns:
                    if col_name and col_name not in columns:
                        columns.append(col_name)
        
        if columns:
            print(f"   ✅ SUCCESS via FieldFolders: {len(columns)} columns")
    
    # ===================================================================
    # METHOD 6: CalculatedFields (for calculated fields)
    # ===================================================================
    print(f"   🔄 Checking CalculatedFields...")
    calc_fields_list = dataset_info.get('CalculatedFields', [])
    
    if calc_fields_list:
        print(f"   ✅ CalculatedFields found: {len(calc_fields_list)} fields")
        
        for calc_field in calc_fields_list:
            field_name = calc_field.get('Name')
            if field_name and field_name not in calculated_fields:
                calculated_fields.append(field_name)
                print(f"      📊 Calculated: {field_name}")
    
    # ===================================================================
    # METHOD 7: LogicalTableMap -> DataTransforms -> CreateColumnsOperation
    # ===================================================================
    print(f"   🔄 Checking DataTransforms in LogicalTableMap...")
    logical_table_map = dataset_info.get('LogicalTableMap', {})
    
    for table_key, table_def in logical_table_map.items():
        data_transforms = table_def.get('DataTransforms', [])
        
        for transform in data_transforms:
            if 'CreateColumnsOperation' in transform:
                create_cols = transform['CreateColumnsOperation'].get('Columns', [])
                print(f"      CreateColumnsOperation: {len(create_cols)} columns")
                
                for col in create_cols:
                    col_name = col.get('ColumnName')
                    if col_name and col_name not in calculated_fields:
                        calculated_fields.append(col_name)
                        print(f"         📊 Transform-created: {col_name}")
    
    # Remove duplicates while preserving order
    columns = list(dict.fromkeys(columns))
    calculated_fields = list(dict.fromkeys(calculated_fields))
    
    # Final summary
    print(f"\n   🎯 FINAL RESULTS for '{dataset_name}':")
    print(f"      Regular columns: {len(columns)}")
    print(f"      Calculated fields: {len(calculated_fields)}")
    
    if not columns and not calculated_fields:
        print(f"   ⚠️ WARNING: No columns found by any method!")
        print(f"   Dataset keys available: {list(dataset_info.keys())}")
    
    return columns, calculated_fields


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
        external_id = payload.get("external_id")

        print(f"Account ID: {account_id}")
        print(f"Region: {region}")
        print(f"Role ARN: {role_arn}")
        print(f"External ID: {external_id}")
        try:
            caller = boto3.client("sts").get_caller_identity()
            print(f"Caller Identity: {caller}")
        except Exception as e:
            print(f"⚠️ Failed to get caller identity: {e}")

        # Get QuickSight client (this will fail if role can't be assumed)
        qs = get_quicksight_client(role_arn, region, external_id)

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
        
        qs = get_quicksight_client(payload.role_arn, payload.region, payload.external_id)
        
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
    """
    List all QuickSight datasets with COMPLETE column and calculated field extraction
    ✅ FIXED: Properly extracts columns from all possible sources
    """
    try:
        print(f"\n{'='*60}")
        print(f"📊 LISTING QUICKSIGHT DATASETS - ENHANCED VERSION")
        print(f"{'='*60}")
        
        qs = get_quicksight_client(payload.role_arn, payload.region, payload.external_id)
        response = qs.list_data_sets(AwsAccountId=payload.aws_account_id)
        
        datasets = []
        dataset_summaries = response.get("DataSetSummaries", [])
        
        print(f"\n📥 Found {len(dataset_summaries)} dataset(s) to process")
        
        for idx, summary in enumerate(dataset_summaries, 1):
            dataset_id = summary["DataSetId"]
            dataset_name = summary["Name"]
            
            print(f"\n{'─'*60}")
            print(f"📦 Dataset {idx}/{len(dataset_summaries)}: {dataset_name}")
            print(f"   ID: {dataset_id}")
            print(f"{'─'*60}")
            
            try:
                # ✅ CRITICAL: Get detailed dataset info
                print(f"   🔍 Calling describe_data_set...")
                dataset_detail = qs.describe_data_set(
                    AwsAccountId=payload.aws_account_id,
                    DataSetId=dataset_id
                )
                
                print(f"   ✅ describe_data_set succeeded")
                
                # ✅ DEBUGGING: Check what we got back
                if 'DataSet' not in dataset_detail:
                    print(f"   ❌ ERROR: No 'DataSet' key in response!")
                    print(f"   Response keys: {list(dataset_detail.keys())}")
                    raise Exception("Invalid describe_data_set response - missing DataSet")
                
                dataset_info = dataset_detail["DataSet"]
                
                # ✅ DEBUG: Print what fields are available
                print(f"   📋 DataSet keys: {list(dataset_info.keys())[:10]}")
                print(f"   Has OutputColumns: {'OutputColumns' in dataset_info}")
                print(f"   Has PhysicalTableMap: {'PhysicalTableMap' in dataset_info}")
                print(f"   Has LogicalTableMap: {'LogicalTableMap' in dataset_info}")
                print(f"   Has CalculatedFields: {'CalculatedFields' in dataset_info}")
                
                # ✅ CHECK OutputColumns first
                output_columns = dataset_info.get('OutputColumns', [])
                print(f"   OutputColumns count: {len(output_columns)}")
                
                if output_columns:
                    # Print first few columns for debugging
                    for i, col in enumerate(output_columns[:3]):
                        print(f"      Sample column {i+1}: {col.get('Name')} ({col.get('Type')})")
                
                # ✅ Use the extraction function
                columns, calculated_fields = extract_columns_from_dataset(dataset_info)
                
                print(f"\n   ✅ EXTRACTION RESULT:")
                print(f"      Regular columns: {len(columns)}")
                print(f"      Calculated fields: {len(calculated_fields)}")
                
                if columns:
                    print(f"      Column names: {', '.join(columns[:5])}" + 
                          (f"... and {len(columns)-5} more" if len(columns) > 5 else ""))
                
                if calculated_fields:
                    print(f"      Calculated: {', '.join(calculated_fields)}")
                
                # ✅ Derive source type (best-effort)
                source_type = "Unknown"
                physical_table_map = dataset_info.get("PhysicalTableMap", {}) or {}
                for _, table_def in physical_table_map.items():
                    if "S3Source" in table_def:
                        source_type = "S3"
                        break
                    if "RelationalTable" in table_def:
                        data_source_arn = table_def["RelationalTable"].get("DataSourceArn", "")
                        if "redshift" in data_source_arn:
                            source_type = "Redshift"
                        elif "athena" in data_source_arn:
                            source_type = "Athena"
                        elif "rds" in data_source_arn:
                            source_type = "RDS"
                        else:
                            source_type = "Relational"
                        break
                    if "CustomSql" in table_def:
                        source_type = "CustomSQL"
                        break

                # ✅ Build the dataset response
                datasets.append({
                    "id": dataset_id,
                    "name": dataset_name,
                    "arn": summary["Arn"],
                    "created_time": str(summary.get("CreatedTime", "")),
                    "last_updated": str(summary.get("LastUpdatedTime", "")),
                    "import_mode": summary.get("ImportMode", "UNKNOWN"),
                    "source_type": source_type,
                    "columns": columns,
                    "calculated_fields": calculated_fields,
                    "column_count": len(columns),
                    "calculated_field_count": len(calculated_fields)
                })
                
                print(f"\n   ✅ SUCCESS: {dataset_name}")
                print(f"      Added {len(columns)} columns and {len(calculated_fields)} calculated fields")
            
            except ClientError as ce:
                error_code = ce.response['Error']['Code']
                error_msg = ce.response['Error']['Message']
                print(f"\n   ❌ AWS ERROR for {dataset_id}:")
                print(f"      Code: {error_code}")
                print(f"      Message: {error_msg}")
                
                # Check if it's a permission issue
                if error_code in ['AccessDeniedException', 'ResourceNotFoundException']:
                    print(f"      This might be a permissions issue or deleted dataset")
                
                # Add basic info on error
                datasets.append({
                    "id": dataset_id,
                    "name": dataset_name,
                    "arn": summary["Arn"],
                    "created_time": str(summary.get("CreatedTime", "")),
                    "last_updated": str(summary.get("LastUpdatedTime", "")),
                    "import_mode": summary.get("ImportMode", "UNKNOWN"),
                    "columns": [],
                    "calculated_fields": [],
                    "column_count": 0,
                    "calculated_field_count": 0,
                    "error": f"{error_code}: {error_msg}"
                })
            
            except Exception as detail_error:
                print(f"\n   ❌ UNEXPECTED ERROR for {dataset_id}:")
                print(f"      Error: {str(detail_error)}")
                import traceback
                print(f"      Traceback:")
                traceback.print_exc()
                
                # Add basic info on error
                datasets.append({
                    "id": dataset_id,
                    "name": dataset_name,
                    "arn": summary["Arn"],
                    "created_time": str(summary.get("CreatedTime", "")),
                    "last_updated": str(summary.get("LastUpdatedTime", "")),
                    "import_mode": summary.get("ImportMode", "UNKNOWN"),
                    "columns": [],
                    "calculated_fields": [],
                    "column_count": 0,
                    "calculated_field_count": 0,
                    "error": str(detail_error)
                })
        
        print(f"\n{'='*60}")
        print(f"✅ COMPLETED: {len(datasets)} dataset(s) processed")
        print(f"{'='*60}")
        
        # ✅ Summary statistics
        total_columns = sum(d['column_count'] for d in datasets)
        total_calc = sum(d['calculated_field_count'] for d in datasets)
        datasets_with_columns = sum(1 for d in datasets if d['column_count'] > 0)
        
        print(f"\n📊 SUMMARY:")
        print(f"   Total datasets: {len(datasets)}")
        print(f"   Datasets with columns: {datasets_with_columns}")
        print(f"   Total columns extracted: {total_columns}")
        print(f"   Total calculated fields: {total_calc}")
        print(f"{'='*60}\n")
        
        return {
            "count": len(datasets),
            "datasets": datasets,
            "summary": {
                "total_columns": total_columns,
                "total_calculated_fields": total_calc,
                "datasets_with_data": datasets_with_columns
            }
        }
    
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        print(f"\n❌ AWS CLIENT ERROR:")
        print(f"   Code: {error_code}")
        print(f"   Message: {error_msg}")
        print(f"{'='*60}\n")
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"AWS Error: {error_code}",
                "message": error_msg
            }
        )
    
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR in list_quicksight_datasets:")
        print(f"   Error: {str(e)}")
        import traceback
        print(f"   Traceback:")
        traceback.print_exc()
        print(f"{'='*60}\n")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to list datasets",
                "message": str(e)
            }
        )

# ==================== QUICKSIGHT DATASET DETAIL ====================

@app.post("/api/quicksight/describe-dataset")
def describe_quicksight_dataset(payload: DescribeDataSetRequest):
    """
    Fetch a single QuickSight dataset schema (columns + calculated fields).
    """
    try:
        dataset_id = payload.dataset_id
        if not dataset_id and payload.dataset_arn:
            dataset_id = payload.dataset_arn.split("/")[-1]

        if not dataset_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "dataset_id required",
                    "message": "Provide dataset_id or dataset_arn"
                }
            )

        qs = get_quicksight_client(payload.role_arn, payload.region, payload.external_id)
        dataset_detail = qs.describe_data_set(
            AwsAccountId=payload.aws_account_id,
            DataSetId=dataset_id
        )

        if "DataSet" not in dataset_detail:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Invalid describe_data_set response",
                    "message": "Missing DataSet in response"
                }
            )

        dataset_info = dataset_detail["DataSet"]
        columns, calculated_fields = extract_columns_from_dataset(dataset_info)

        return {
            "status": "success",
            "dataset_id": dataset_id,
            "name": dataset_info.get("Name"),
            "arn": dataset_info.get("Arn"),
            "columns": columns,
            "calculated_fields": calculated_fields,
            "column_count": len(columns),
            "calculated_field_count": len(calculated_fields)
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to describe dataset",
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
        
        qs = get_quicksight_client(payload.role_arn, payload.region, payload.external_id)
        
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

# ==================== DOMO CARD CREATION ====================

def get_domo_client() -> DomoClient:
    base_url = (
        os.environ.get("DOMO_BASE_URL")
        or os.environ.get("DOMO_INSTANCE_URL")
        or os.environ.get("DOMO_INSTANCE")
    )
    if not base_url:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Domo config missing",
                "message": "Set DOMO_BASE_URL (e.g., https://gwcteq-partner.domo.com)"
            }
        )

    client_id = os.environ.get("DOMO_CLIENT_ID")
    client_secret = os.environ.get("DOMO_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Domo credentials missing",
                "message": "Set DOMO_CLIENT_ID and DOMO_CLIENT_SECRET in backend env"
            }
        )

    token = get_domo_access_token(client_id, client_secret)

    # Decode token payload for debugging scopes (no signature verification)
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
        payload = json.loads(payload_json)
        scope = payload.get("scope")
        print(f"DOMO OAuth scopes: {scope}")
    except Exception as decode_error:
        print(f"⚠️ Could not decode token payload: {decode_error}")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    return DomoClient(base_url=base_url, headers=headers)


@app.post("/api/domo/create-card")
def create_domo_card(payload: CreateDomoCardRequest):
    """
    Create a KPI card in Domo using server-side auth.
    """
    try:
        if not payload.dataset_id:
            raise HTTPException(status_code=400, detail={
                "error": "dataset_id required",
                "message": "No dataset_id provided"
            })

        domo = get_domo_client()

        card_payload = {
            "definition": {
                "title": payload.title or "Migrated Visual",
                "description": payload.description or f"Migrated from QuickSight - {payload.visual_type or 'Visual'}",
                "cardType": "kpi",
                "visualization": {
                    "type": "single_value",
                    "settings": {
                        "showValue": True,
                        "showChange": False,
                        "formatting": {
                            "decimalPlaces": 0
                        }
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": payload.dataset_id,
                "query": {
                    "fields": [
                        {
                            "columnName": "value",
                            "function": "count"
                        }
                    ],
                    "filters": [],
                    "sorts": []
                }
            }
        }

        result = domo.create_card(payload.page_id, card_payload)
        return {
            "status": "success",
            "card": result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to create Domo card",
                "message": str(e)
            }
        )

# ==================== DOMO DEBUG ====================

@app.get("/api/domo/debug")
def domo_debug():
    """
    Debug Domo OAuth and API access.
    Returns env snapshot (non-secret), token scopes, and a basic API probe.
    """
    try:
        base_url = (
            os.environ.get("DOMO_BASE_URL")
            or os.environ.get("DOMO_INSTANCE_URL")
            or os.environ.get("DOMO_INSTANCE")
        )
        client_id = os.environ.get("DOMO_CLIENT_ID")
        client_secret = os.environ.get("DOMO_CLIENT_SECRET")
        oauth_scope = os.environ.get("DOMO_OAUTH_SCOPE", "dashboard data")

        if not base_url or not client_id or not client_secret:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Domo config missing",
                    "message": "DOMO_BASE_URL / DOMO_CLIENT_ID / DOMO_CLIENT_SECRET must be set"
                }
            )

        token = get_domo_access_token(client_id, client_secret)

        # Decode token payload for scopes (no signature verification)
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
        payload = json.loads(payload_json)
        token_scopes = payload.get("scope")

        # Probe a basic endpoint to validate auth
        probe_url = f"{base_url.rstrip('/')}/api/content/v3/cards"
        probe_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        probe_resp = requests.get(probe_url, headers=probe_headers)

        return {
            "env": {
                "DOMO_BASE_URL": base_url,
                "DOMO_OAUTH_SCOPE": oauth_scope,
                "DOMO_CLIENT_ID_prefix": client_id[:6] if client_id else None
            },
            "token_scopes": token_scopes,
            "probe": {
                "url": probe_url,
                "status": probe_resp.status_code,
                "response_text": probe_resp.text[:1000]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Domo debug failed",
                "message": str(e)
            }
        )

# ==================== DOMO DATASET DETAIL (INSTANCE PROXY) ====================

@app.post("/api/domo/dataset-detail")
def domo_dataset_detail(payload: DomoDatasetDetailRequest):
    """
    Fetch Domo dataset details + schema from instance URLs.
    Uses OAuth token and instance base URL.
    """
    try:
        base_url = (
            os.environ.get("DOMO_BASE_URL")
            or os.environ.get("DOMO_INSTANCE_URL")
            or os.environ.get("DOMO_INSTANCE")
        )
        if not base_url:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Domo config missing",
                    "message": "Set DOMO_BASE_URL (e.g., https://gwcteq-partner.domo.com)"
                }
            )

        client_id = os.environ.get("DOMO_CLIENT_ID")
        client_secret = os.environ.get("DOMO_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Domo credentials missing",
                    "message": "Set DOMO_CLIENT_ID and DOMO_CLIENT_SECRET in backend env"
                }
            )

        token = get_domo_access_token(client_id, client_secret)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        dataset_id = payload.dataset_id
        details_url = f"{base_url.rstrip('/')}/api/data/v3/datasources/{dataset_id}?includeAllDetails=true&includePrivate=true"
        schema_url = f"https://api.domo.com/v1/datasets/{dataset_id}/schema"

        details_resp = requests.get(details_url, headers=headers)
        if details_resp.status_code != 200:
            raise HTTPException(
                status_code=details_resp.status_code,
                detail={
                    "error": "Failed to fetch dataset details",
                    "message": details_resp.text
                }
            )

        schema_resp = requests.get(schema_url, headers=headers)
        if schema_resp.status_code != 200:
            raise HTTPException(
                status_code=schema_resp.status_code,
                detail={
                    "error": "Failed to fetch dataset schema",
                    "message": schema_resp.text
                }
            )

        return {
            "status": "success",
            "dataset": details_resp.json(),
            "schema": schema_resp.json()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Domo dataset detail failed",
                "message": str(e)
            }
        )


# ==================== DOMO DATASET SEARCH (INDEXED) ====================

@app.get("/api/domo/datasets/search")
def search_domo_datasets_endpoint(
    q: str = Query("", description="Search term"),
    limit: Optional[int] = Query(50, ge=1),
    offset: int = Query(0, ge=0)
):
    """
    Search Domo datasets by name using cached backend index.
    Returns minimal {id, name} entries.
    """
    try:
        warm_index_async()
        payload = search_domo_datasets(q, limit, offset)
        results = payload["results"]
        total = payload["total"]
        return {
            "status": "success",
            "count": len(results),
            "total": total,
            "datasets": results,
            "cache": get_domo_dataset_index_status(),
            "warming": payload.get("warming", False)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Domo dataset search failed",
                "message": str(e)
            }
        )


@app.post("/api/domo/datasets/refresh")
def refresh_domo_datasets_endpoint():
    """
    Force refresh the Domo dataset index cache.
    """
    try:
        data = refresh_domo_dataset_index()
        status = get_domo_dataset_index_status()
        return {
            "status": "success",
            "count": len(data),
            "cache": status
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Domo dataset index refresh failed",
                "message": str(e)
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

# ==================== DOMO CARD CONFIGS (FOR CODEENGINE) ====================

@app.post("/api/transform/unified-to-domo-configs")
def transform_to_domo_configs(payload: TransformToDomoRequest):
    """
    Transform unified schema to full Domo card configs (definition/dataProvider/variables).
    Intended for frontend codeengine createcard flow.
    """
    try:
        print(f"\n{'='*60}")
        print(f"🔧 BUILDING DOMO CARD CONFIGS")
        print(f"{'='*60}")

        unified = payload.unified_schema
        dataset_mapping = payload.dataset_mapping

        resolver = StaticDatasetResolver(dataset_mapping)
        adapter = DomoAdapter(domo_client=None, dataset_resolver=resolver, column_mapping={})
        adapter._process_calculated_fields(unified.get("calculatedFields", []))

        card_configs = []
        errors = []

        for page in unified.get("pages", []):
            page_name = page.get("name") or page.get("pageName") or page.get("title") or "Untitled Sheet"
            page_id = page.get("id") or page.get("pageId")
            for visual in page.get("visuals", []):
                try:
                    config = adapter.build_card_config(visual)
                    card_configs.append({
                        "visual_id": visual.get("id"),
                        "visual_type": visual.get("type"),
                        "title": visual.get("title", "Untitled Visual"),
                        "config": config,
                        "page_name": page_name,
                        "page_id": page_id
                    })
                    print(f"   ✅ Built config for {visual.get('type')}: {visual.get('title')}")
                except Exception as visual_error:
                    errors.append({
                        "visual_id": visual.get("id"),
                        "error": str(visual_error)
                    })
                    print(f"   ❌ Failed config for {visual.get('type')}: {visual_error}")

        print(f"\n{'='*60}")
        print(f"✅ Built {len(card_configs)} card config(s)")
        if errors:
            print(f"⚠️  {len(errors)} error(s) occurred")
        print(f"{'='*60}\n")

        return {
            "status": "success",
            "card_count": len(card_configs),
            "error_count": len(errors),
            "card_configs": card_configs,
            "errors": errors
        }

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Config transformation failed: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Transformation to Domo configs failed",
                "message": error_msg
            }
        )

@app.post("/api/quicksight/describe-dataset-with-source")
def describe_dataset_with_source(payload: DescribeDataSetWithSourceRequest):
    """
    ✅ PHASE 1: Enhanced dataset description that includes datasource metadata
    
    This endpoint extends the existing describe-dataset to also extract:
    - Datasource type (Snowflake, Redshift, S3, etc.)
    - Connection properties (database, schema, table, warehouse)
    - Datasource name and ID
    
    Use this for the Dataset Mapping step to show datasource information
    """
    try:
        print(f"\n{'='*60}")
        print(f"🔍 DESCRIBE DATASET WITH SOURCE")
        print(f"{'='*60}")
        
        # Get QuickSight client
        qs = get_quicksight_client(payload.role_arn, payload.region, payload.external_id)
        
        # Determine dataset ID
        if payload.dataset_id:
            dataset_id = payload.dataset_id
        elif payload.dataset_arn:
            dataset_id = payload.dataset_arn.split('/')[-1]
        else:
            raise HTTPException(
                status_code=400,
                detail={"error": "Either dataset_id or dataset_arn is required"}
            )
        
        print(f"Dataset ID: {dataset_id}")
        
        # Describe the dataset
        dataset_response = qs.describe_data_set(
            AwsAccountId=payload.aws_account_id,
            DataSetId=dataset_id
        )
        
        dataset = dataset_response['DataSet']
        print(f"Dataset Name: {dataset.get('Name')}")
        
        # ✅ NEW: Extract datasource metadata
        print(f"\n🔍 Extracting datasource metadata...")
        datasource_info = extract_datasource_metadata(
            qs,
            payload.aws_account_id,
            dataset
        )
        
        print(f"\n✅ Datasource Detection Results:")
        print(f"   Type: {datasource_info['type']}")
        print(f"   Name: {datasource_info['name']}")
        print(f"   ID: {datasource_info['id']}")
        
        if datasource_info['type'] == 'SNOWFLAKE':
            props = datasource_info['connection_properties']
            print(f"   Snowflake Table: {props.get('database')}.{props.get('schema')}.{props.get('table')}")
            print(f"   Warehouse: {props.get('warehouse')}")
            print(f"   Host: {props.get('host')}")
        
        print(f"{'='*60}\n")
        
        return {
            "status": "success",
            "dataset": {
                "DataSetId": dataset.get('DataSetId'),
                "Name": dataset.get('Name'),
                "Arn": dataset.get('Arn'),
                "CreatedTime": dataset.get('CreatedTime').isoformat() if dataset.get('CreatedTime') else None,
                "LastUpdatedTime": dataset.get('LastUpdatedTime').isoformat() if dataset.get('LastUpdatedTime') else None,
                "ImportMode": dataset.get('ImportMode'),
                "OutputColumns": dataset.get('OutputColumns', [])
            },
            "datasource": datasource_info  # ✅ NEW: Datasource metadata
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        print(f"❌ AWS Error: {error_code} - {error_msg}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": f"AWS Error ({error_code})",
                "message": error_msg
            }
        )
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to describe dataset with source",
                "message": error_msg
            }
        )


@app.post("/api/quicksight/list-datasets-with-sources")
def list_datasets_with_sources(payload: ListDataSetsRequest):
    """
    ✅ PHASE 1: Enhanced dataset listing that includes datasource metadata
    
    This is a more expensive operation than list-datasets because it:
    1. Lists all datasets
    2. Describes each dataset to get datasource info
    
    Use this sparingly or implement caching/pagination
    """
    try:
        print(f"\n{'='*60}")
        print(f"📊 LIST DATASETS WITH SOURCES")
        print(f"{'='*60}")
        
        # Get QuickSight client
        qs = get_quicksight_client(payload.role_arn, payload.region, payload.external_id)
        
        # List datasets
        print(f"Listing datasets for account: {payload.aws_account_id}")
        response = qs.list_data_sets(AwsAccountId=payload.aws_account_id)
        
        datasets_summary = response.get('DataSetSummaries', [])
        print(f"Found {len(datasets_summary)} datasets")
        
        # Enrich with datasource info
        enriched_datasets = []
        
        for i, dataset_summary in enumerate(datasets_summary, 1):
            dataset_id = dataset_summary['DataSetId']
            dataset_name = dataset_summary['Name']
            
            print(f"\n[{i}/{len(datasets_summary)}] Processing: {dataset_name}")
            
            try:
                # Get full dataset details
                dataset_response = qs.describe_data_set(
                    AwsAccountId=payload.aws_account_id,
                    DataSetId=dataset_id
                )
                
                dataset = dataset_response['DataSet']
                
                # Extract datasource metadata
                datasource_info = extract_datasource_metadata(
                    qs,
                    payload.aws_account_id,
                    dataset
                )
                
                print(f"   Type: {datasource_info['type']}")
                
                enriched_datasets.append({
                    "DataSetId": dataset_id,
                    "Name": dataset_name,
                    "Arn": dataset_summary.get('Arn'),
                    "CreatedTime": dataset_summary.get('CreatedTime').isoformat() if dataset_summary.get('CreatedTime') else None,
                    "LastUpdatedTime": dataset_summary.get('LastUpdatedTime').isoformat() if dataset_summary.get('LastUpdatedTime') else None,
                    "ImportMode": dataset_summary.get('ImportMode'),
                    "RowCount": dataset.get('RowLevelPermissionDataSet', {}).get('RowCount'),
                    "Columns": [col.get('Name') for col in dataset.get('OutputColumns', [])],
                    "datasource": datasource_info  # ✅ NEW
                })
                
            except Exception as dataset_error:
                print(f"   ⚠️ Error processing dataset: {dataset_error}")
                # Include dataset even if datasource detection fails
                enriched_datasets.append({
                    "DataSetId": dataset_id,
                    "Name": dataset_name,
                    "Arn": dataset_summary.get('Arn'),
                    "datasource": {
                        "type": "UNKNOWN",
                        "error": str(dataset_error)
                    }
                })
        
        # Group by datasource type
        by_type = {}
        for ds in enriched_datasets:
            ds_type = ds['datasource']['type']
            if ds_type not in by_type:
                by_type[ds_type] = []
            by_type[ds_type].append(ds)
        
        print(f"\n{'='*60}")
        print(f"✅ DATASOURCE SUMMARY")
        print(f"{'='*60}")
        for ds_type, datasets in by_type.items():
            print(f"{ds_type}: {len(datasets)} dataset(s)")
        print(f"{'='*60}\n")
        
        return {
            "status": "success",
            "count": len(enriched_datasets),
            "datasets": enriched_datasets,
            "summary_by_type": {
                ds_type: len(datasets)
                for ds_type, datasets in by_type.items()
            }
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        print(f"❌ AWS Error: {error_code} - {error_msg}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": f"AWS Error ({error_code})",
                "message": error_msg
            }
        )
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to list datasets with sources",
                "message": error_msg
            }
        )


@app.get("/api/quicksight/supported-datasources")
def get_supported_datasources():
    """
    Get list of supported datasource types
    
    This is a simple info endpoint for the frontend
    """
    return {
        "status": "success",
        "supported_types": [
            {
                "type": "SNOWFLAKE",
                "name": "Snowflake",
                "description": "Snowflake data warehouse",
                "color": "#29B5E8"
            },
            {
                "type": "REDSHIFT",
                "name": "Amazon Redshift",
                "description": "Amazon Redshift data warehouse",
                "color": "#8C4FFF"
            },
            {
                "type": "POSTGRES",
                "name": "PostgreSQL",
                "description": "PostgreSQL database",
                "color": "#336791"
            },
            {
                "type": "MYSQL",
                "name": "MySQL",
                "description": "MySQL database",
                "color": "#4479A1"
            },
            {
                "type": "MARIADB",
                "name": "MariaDB",
                "description": "MariaDB database",
                "color": "#003545"
            },
            {
                "type": "ATHENA",
                "name": "Amazon Athena",
                "description": "Amazon Athena query service",
                "color": "#FF9900"
            },
            {
                "type": "S3",
                "name": "Amazon S3",
                "description": "Amazon S3 storage",
                "color": "#569A31"
            }
        ]
    }

# ==================== DATASET REGISTRY (PHASE 2) ====================

@app.post("/api/datasets/register")
def register_dataset(payload: RegisterDatasetRequest):
    """
    Register a QuickSight dataset with datasource metadata and optional Domo mapping
    """
    try:
        dataset_registry.register_dataset(
            qs_dataset_id=payload.qs_dataset_id,
            qs_dataset_name=payload.qs_dataset_name,
            datasource_type=payload.datasource_type,
            connection_properties=payload.connection_properties,
            domo_dataset_id=payload.domo_dataset_id
        )
        return {
            "status": "success",
            "message": "Dataset registered"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to register dataset",
                "message": str(e)
            }
        )


@app.post("/api/datasets/suggest-match")
def suggest_domo_match(payload: SuggestMatchRequest):
    """
    Suggest Domo dataset match for a QuickSight dataset
    """
    try:
        suggestion = dataset_registry.suggest_domo_match(
            qs_dataset_id=payload.qs_dataset_id,
            available_domo_datasets=payload.domo_datasets
        )
        return {
            "status": "success",
            "suggested_domo_id": suggestion
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to suggest match",
                "message": str(e)
            }
        )


# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))

    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)

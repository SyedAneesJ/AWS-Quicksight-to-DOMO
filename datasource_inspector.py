"""
Datasource Inspector - Extract datasource metadata from QuickSight datasets

This module detects and extracts connection information for various datasources:
- Snowflake
- Redshift
- RDS (PostgreSQL, MySQL)
- S3
- Athena

Author: QuickSight to Domo Migration Tool
Version: 1.0.0
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class DataSourceInspector:
    """
    Inspects QuickSight datasets to determine datasource type and connection details
    """
    
    # Supported datasource types
    SUPPORTED_TYPES = [
        'SNOWFLAKE',
        'REDSHIFT',
        'POSTGRES',
        'MYSQL',
        'MARIADB',
        'ATHENA',
        'S3',
        'SPICE'
    ]
    
    def __init__(self, quicksight_client):
        """
        Initialize inspector with QuickSight client
        
        Args:
            quicksight_client: boto3 QuickSight client
        """
        self.qs_client = quicksight_client
    
    def inspect_dataset(self, aws_account_id: str, dataset: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inspect a QuickSight dataset to extract datasource information
        
        Args:
            aws_account_id: AWS account ID
            dataset: QuickSight dataset object from describe_data_set()
        
        Returns:
            {
                "type": "SNOWFLAKE" | "REDSHIFT" | "S3" | ...,
                "name": "datasource name",
                "id": "datasource-id",
                "connection_properties": {
                    "database": "...",
                    "schema": "...",
                    "table": "...",
                    # ... source-specific properties
                }
            }
        """
        
        datasource_info = {
            "type": "UNKNOWN",
            "name": None,
            "id": None,
            "connection_properties": {},
            "import_mode": dataset.get('ImportMode', 'UNKNOWN')
        }
        
        try:
            # Extract from PhysicalTableMap
            physical_table_map = dataset.get('PhysicalTableMap', {})
            
            if not physical_table_map:
                logger.warning(f"No PhysicalTableMap found for dataset {dataset.get('DataSetId')}")
                return datasource_info
            
            # Iterate through physical tables
            for table_key, table_def in physical_table_map.items():
                logger.info(f"Inspecting physical table: {table_key}")
                
                # ========================================
                # RELATIONAL TABLE (Snowflake, Redshift, RDS, etc.)
                # ========================================
                if 'RelationalTable' in table_def:
                    relational = table_def['RelationalTable']
                    datasource_arn = relational.get('DataSourceArn')
                    
                    if datasource_arn:
                        # Get datasource details
                        ds_info = self._inspect_relational_datasource(
                            aws_account_id,
                            datasource_arn,
                            relational
                        )
                        
                        if ds_info['type'] != 'UNKNOWN':
                            return ds_info
                
                # ========================================
                # S3 SOURCE
                # ========================================
                elif 'S3Source' in table_def:
                    s3_source = table_def['S3Source']
                    datasource_arn = s3_source.get('DataSourceArn')
                    
                    datasource_info['type'] = 'S3'
                    datasource_info['connection_properties'] = {
                        'datasource_arn': datasource_arn,
                        'upload_settings': s3_source.get('UploadSettings', {}),
                        'input_columns': [col.get('Name') for col in s3_source.get('InputColumns', [])]
                    }
                    
                    if datasource_arn:
                        datasource_id = datasource_arn.split('/')[-1]
                        datasource_info['id'] = datasource_id
                        
                        try:
                            ds_response = self.qs_client.describe_data_source(
                                AwsAccountId=aws_account_id,
                                DataSourceId=datasource_id
                            )
                            datasource_info['name'] = ds_response['DataSource'].get('Name')
                        except Exception as e:
                            logger.warning(f"Could not describe S3 datasource: {e}")
                    
                    return datasource_info
                
                # ========================================
                # CUSTOM SQL
                # ========================================
                elif 'CustomSql' in table_def:
                    custom_sql = table_def['CustomSql']
                    datasource_arn = custom_sql.get('DataSourceArn')
                    
                    if datasource_arn:
                        datasource_id = datasource_arn.split('/')[-1]
                        
                        try:
                            ds_response = self.qs_client.describe_data_source(
                                AwsAccountId=aws_account_id,
                                DataSourceId=datasource_id
                            )
                            
                            datasource = ds_response['DataSource']
                            datasource_type = datasource.get('Type', 'UNKNOWN')
                            
                            datasource_info['type'] = datasource_type
                            datasource_info['name'] = datasource.get('Name')
                            datasource_info['id'] = datasource_id
                            datasource_info['connection_properties'] = {
                                'custom_sql': custom_sql.get('SqlQuery'),
                                'columns': [col.get('Name') for col in custom_sql.get('Columns', [])]
                            }
                            
                            # Add source-specific params
                            params = datasource.get('DataSourceParameters', {})
                            if datasource_type == 'SNOWFLAKE':
                                snowflake_params = params.get('SnowflakeParameters', {})
                                datasource_info['connection_properties'].update({
                                    'database': snowflake_params.get('Database'),
                                    'warehouse': snowflake_params.get('Warehouse'),
                                    'host': snowflake_params.get('Host')
                                })
                            
                            return datasource_info
                            
                        except Exception as e:
                            logger.error(f"Error inspecting CustomSql datasource: {e}")
            
            return datasource_info
            
        except Exception as e:
            logger.error(f"Error inspecting dataset: {e}")
            import traceback
            traceback.print_exc()
            return datasource_info
    
    def _inspect_relational_datasource(
        self,
        aws_account_id: str,
        datasource_arn: str,
        relational_table: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Inspect a relational datasource (Snowflake, Redshift, RDS, etc.)
        
        Args:
            aws_account_id: AWS account ID
            datasource_arn: ARN of the datasource
            relational_table: RelationalTable definition
        
        Returns:
            Datasource info dict
        """
        
        datasource_info = {
            "type": "UNKNOWN",
            "name": None,
            "id": None,
            "connection_properties": {}
        }
        
        try:
            # Extract datasource ID from ARN
            datasource_id = datasource_arn.split('/')[-1]
            datasource_info['id'] = datasource_id
            
            # Describe the datasource
            logger.info(f"Describing datasource: {datasource_id}")
            ds_response = self.qs_client.describe_data_source(
                AwsAccountId=aws_account_id,
                DataSourceId=datasource_id
            )
            
            datasource = ds_response['DataSource']
            datasource_type = datasource.get('Type', 'UNKNOWN')
            
            datasource_info['type'] = datasource_type
            datasource_info['name'] = datasource.get('Name')
            
            # Extract base table info
            schema = relational_table.get('Schema')
            table_name = relational_table.get('Name')
            catalog = relational_table.get('Catalog')
            
            # Get datasource parameters
            params = datasource.get('DataSourceParameters', {})
            
            # ========================================
            # SNOWFLAKE
            # ========================================
            if datasource_type == 'SNOWFLAKE':
                snowflake_params = params.get('SnowflakeParameters', {})
                
                datasource_info['connection_properties'] = {
                    'database': snowflake_params.get('Database'),
                    'schema': schema,
                    'table': table_name,
                    'warehouse': snowflake_params.get('Warehouse'),
                    'host': snowflake_params.get('Host'),
                    'catalog': catalog
                }
                
                logger.info(f"✅ Detected Snowflake datasource: {datasource_info['name']}")
                logger.info(f"   Table: {datasource_info['connection_properties']['database']}.{schema}.{table_name}")
            
            # ========================================
            # REDSHIFT
            # ========================================
            elif datasource_type == 'REDSHIFT':
                redshift_params = params.get('RedshiftParameters', {})
                
                datasource_info['connection_properties'] = {
                    'database': redshift_params.get('Database'),
                    'schema': schema,
                    'table': table_name,
                    'cluster_id': redshift_params.get('ClusterId'),
                    'host': redshift_params.get('Host'),
                    'port': redshift_params.get('Port', 5439)
                }
                
                logger.info(f"✅ Detected Redshift datasource: {datasource_info['name']}")
            
            # ========================================
            # RDS POSTGRES
            # ========================================
            elif datasource_type == 'POSTGRES':
                postgres_params = params.get('PostgreSqlParameters', {})
                
                datasource_info['connection_properties'] = {
                    'database': postgres_params.get('Database'),
                    'schema': schema,
                    'table': table_name,
                    'host': postgres_params.get('Host'),
                    'port': postgres_params.get('Port', 5432)
                }
                
                logger.info(f"✅ Detected PostgreSQL datasource: {datasource_info['name']}")
            
            # ========================================
            # RDS MYSQL
            # ========================================
            elif datasource_type == 'MYSQL':
                mysql_params = params.get('MySqlParameters', {})
                
                datasource_info['connection_properties'] = {
                    'database': mysql_params.get('Database'),
                    'schema': schema,
                    'table': table_name,
                    'host': mysql_params.get('Host'),
                    'port': mysql_params.get('Port', 3306)
                }
                
                logger.info(f"✅ Detected MySQL datasource: {datasource_info['name']}")
            
            # ========================================
            # MARIADB
            # ========================================
            elif datasource_type == 'MARIADB':
                mariadb_params = params.get('MariaDbParameters', {})
                
                datasource_info['connection_properties'] = {
                    'database': mariadb_params.get('Database'),
                    'schema': schema,
                    'table': table_name,
                    'host': mariadb_params.get('Host'),
                    'port': mariadb_params.get('Port', 3306)
                }
                
                logger.info(f"✅ Detected MariaDB datasource: {datasource_info['name']}")
            
            # ========================================
            # ATHENA
            # ========================================
            elif datasource_type == 'ATHENA':
                athena_params = params.get('AthenaParameters', {})
                
                datasource_info['connection_properties'] = {
                    'database': catalog,  # Athena uses catalog as database
                    'schema': schema,
                    'table': table_name,
                    'work_group': athena_params.get('WorkGroup')
                }
                
                logger.info(f"✅ Detected Athena datasource: {datasource_info['name']}")
            
            else:
                logger.warning(f"⚠️ Unsupported datasource type: {datasource_type}")
                datasource_info['connection_properties'] = {
                    'schema': schema,
                    'table': table_name,
                    'catalog': catalog
                }
            
            return datasource_info
            
        except Exception as e:
            logger.error(f"Error inspecting relational datasource: {e}")
            import traceback
            traceback.print_exc()
            return datasource_info
    
    def get_datasource_summary(self, datasource_info: Dict[str, Any]) -> str:
        """
        Get a human-readable summary of the datasource
        
        Args:
            datasource_info: Datasource info dict
        
        Returns:
            Summary string
        """
        ds_type = datasource_info.get('type', 'UNKNOWN')
        ds_name = datasource_info.get('name', 'Unknown')
        props = datasource_info.get('connection_properties', {})
        
        if ds_type == 'SNOWFLAKE':
            return f"Snowflake: {props.get('database')}.{props.get('schema')}.{props.get('table')}"
        
        elif ds_type == 'REDSHIFT':
            return f"Redshift: {props.get('database')}.{props.get('schema')}.{props.get('table')}"
        
        elif ds_type in ['POSTGRES', 'MYSQL', 'MARIADB']:
            return f"{ds_type}: {props.get('database')}.{props.get('schema')}.{props.get('table')}"
        
        elif ds_type == 'S3':
            return f"S3: {ds_name}"
        
        elif ds_type == 'ATHENA':
            return f"Athena: {props.get('database')}.{props.get('schema')}.{props.get('table')}"
        
        else:
            return f"{ds_type}: {ds_name}"


def extract_datasource_metadata(
    qs_client,
    aws_account_id: str,
    dataset: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Convenience function to extract datasource metadata from a QuickSight dataset
    
    Args:
        qs_client: boto3 QuickSight client
        aws_account_id: AWS account ID
        dataset: QuickSight dataset object
    
    Returns:
        Datasource info dict
    """
    inspector = DataSourceInspector(qs_client)
    return inspector.inspect_dataset(aws_account_id, dataset)
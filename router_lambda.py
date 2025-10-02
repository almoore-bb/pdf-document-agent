import json
import boto3
from typing import Dict, Any

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Router Lambda function to route requests to appropriate handlers
    """
    try:
        api_path = event.get('apiPath', '')
        
        # Route based on API path
        if api_path == '/analyze-accessibility':
            return analyze_accessibility(event, context)
        elif api_path == '/fix-accessibility':
            return fix_accessibility(event, context)
        else:
            return create_error_response("Unknown API path", api_path)
            
    except Exception as e:
        return create_error_response(f"Router error: {str(e)}", event.get('apiPath', ''))

def analyze_accessibility(event: Dict[str, Any], context) -> Dict[str, Any]:
    """Invoke the document analyzer Lambda"""
    lambda_client = boto3.client('lambda')
    
    response = lambda_client.invoke(
        FunctionName='ally-document-analyzer',
        Payload=json.dumps(event)
    )
    
    return json.loads(response['Payload'].read())

def fix_accessibility(event: Dict[str, Any], context) -> Dict[str, Any]:
    """Invoke the document fixer Lambda"""
    lambda_client = boto3.client('lambda')
    
    response = lambda_client.invoke(
        FunctionName='ally-document-fixer',
        Payload=json.dumps(event)
    )
    
    return json.loads(response['Payload'].read())

def create_error_response(message: str, api_path: str) -> Dict[str, Any]:
    """Create error response"""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': 'DocumentAnalysisGroup',
            'apiPath': api_path,
            'httpMethod': 'POST',
            'httpStatusCode': 400,
            'responseBody': {
                'application/json': {
                    'body': json.dumps({'error': message})
                }
            }
        }
    }
import json
import boto3
import base64
from typing import Dict, Any
import PyPDF2
import io

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to analyze document accessibility using Bedrock
    """
    try:
        # Parse the event from Bedrock Agent
        action_group = event.get('actionGroup', '')
        api_path = event.get('apiPath', '')
        http_method = event.get('httpMethod', '')
        parameters = event.get('parameters', [])
        
        # Extract document from parameters
        document_content = None
        document_type = None
        
        for param in parameters:
            if param['name'] == 'document':
                document_content = param['value']
            elif param['name'] == 'document_type':
                document_type = param['value']
        
        if not document_content:
            return create_response(f"Error: No document provided. Event: {json.dumps(event)}", api_path)
        
        # Initialize Bedrock client
        bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
        
        # Handle different document formats
        if document_content.startswith('s3://'):
            # Extract text from S3 PDF
            decoded_content = extract_pdf_from_s3(document_content)
        else:
            # Handle base64 or plain text
            try:
                decoded_content = base64.b64decode(document_content).decode('utf-8')
            except:
                decoded_content = document_content
        
        # Create prompt for accessibility analysis
        prompt = f"""
        Analyze the following {document_type or 'document'} content for accessibility issues according to WCAG guidelines:
        
        {decoded_content}
        
        Please provide:
        1. List of accessibility problems found
        2. WCAG guideline violations
        3. Specific recommendations for fixes
        4. Priority level for each issue (High/Medium/Low)
        
        Format the response as a structured analysis.
        """
        
        # Call Bedrock model
        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-5-sonnet-20240620-v1:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
        )
        
        # Parse response
        result = json.loads(response['body'].read())
        accessibility_analysis = result['content'][0]['text']
        
        if api_path == '/fix-accessibility':
            # For fix requests, call the fixer Lambda
            lambda_client = boto3.client('lambda')
            fix_response = lambda_client.invoke(
                FunctionName='ally-document-fixer',
                Payload=json.dumps(event)
            )
            return json.loads(fix_response['Payload'].read())
        else:
            return create_response(accessibility_analysis, api_path)
        
    except Exception as e:
        return create_response(f"Error analyzing document: {str(e)}", event.get('apiPath', ''))

def extract_pdf_from_s3(s3_uri: str) -> str:
    """Extract text from PDF stored in S3"""
    s3 = boto3.client('s3')
    
    # Parse S3 URI
    bucket = s3_uri.replace('s3://', '').split('/')[0]
    key = '/'.join(s3_uri.replace('s3://', '').split('/')[1:])
    
    # Download PDF from S3
    response = s3.get_object(Bucket=bucket, Key=key)
    pdf_content = response['Body'].read()
    
    # Extract text using PyPDF2
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n"
    
    return text

def create_response(content: str, api_path: str) -> Dict[str, Any]:
    """Create properly formatted response for Bedrock Agent"""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': 'DocumentAnalysisGroup',
            'apiPath': api_path,
            'httpMethod': 'POST',
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {
                    'body': json.dumps({'analysis': content})
                }
            }
        }
    }
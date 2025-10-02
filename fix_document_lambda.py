import json
import boto3
import base64
import uuid
import logging
import fitz
import pymupdf4llm
from typing import Dict, Any
import io
import re

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to fix document accessibility issues using Bedrock
    """
    try:
        # Log the full event for debugging
        logger.info(f"Fix Lambda received event: {json.dumps(event, indent=2)}")
        
        # Parse the event from Bedrock Agent
        api_path = event.get('apiPath', '')
        parameters = event.get('parameters', [])
        
        # Log parsed parameters
        logger.info(f"API Path: {api_path}")
        logger.info(f"Parameters: {json.dumps(parameters, indent=2)}")
        
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
        
        # Initialize AWS clients
        bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
        s3 = boto3.client('s3')
        
        # Handle different document formats
        if document_content.startswith('s3://'):
            # Extract text from S3 PDF
            decoded_content = extract_pdf_from_s3(document_content)
            logger.info(f"Extracted PDF content from S3: {document_content}")
        else:
            # Handle base64 or plain text
            try:
                decoded_content = base64.b64decode(document_content).decode('utf-8')
            except:
                decoded_content = document_content
        
        logger.info(f"Document content length: {len(decoded_content)} characters")
        
        # Get accessibility fixes from Claude
        prompt = f"""
        Analyze this {document_type or 'document'} content and provide accessibility fixes according to WCAG guidelines.
        
        Content: {decoded_content}
        
        Please provide:
        1. Corrected content with proper heading structure (H1, H2, H3)
        2. Alt text for any images mentioned
        3. Proper table headers if tables are present
        4. Color contrast improvements
        5. Clear, descriptive link text
        
        Return the corrected content in Markdown format, including the alt text for images and table headers.
        Do not include any other text in the response, only the corrected content.
       
        """
        
        # Log the prompt being sent to the model
        logger.info(f"Sending prompt to Bedrock model: {prompt[:500]}...")
        
        streaming_response = bedrock.invoke_model_with_response_stream(
            modelId='global.anthropic.claude-sonnet-4-20250514-v1:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "system": "You are an assistant that fixes accessibility issues in documents.",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.0
            })
        )
        fixed_content = ""
        stream = streaming_response.get('body')
        if not stream:
            raise ValueError("No response from Bedrock model")
        for evt in stream:
            if evt:
                chunk = json.loads(evt['chunk']['bytes'])
                if chunk['type'] == 'content_block_delta':
                    text = chunk['delta']['text']
                    fixed_content += text
 
        logger.info(f"Received fixed content from Bedrock model: {fixed_content[:1500]}...")

        # Upload markdown to S3
        bucket_name = 'ally-kb-supplemental-storage'
        file_key = f'fixed-documents/{uuid.uuid4()}.md'
        
        s3.put_object(
            Bucket=bucket_name,
            Key=file_key,
            Body=fixed_content.encode('utf-8'),
            ContentType='text/markdown',
            Metadata={
                'accessibility-fixed': 'true',
                'original-type': document_type or 'unknown'
            }
        )
        
        # Generate presigned URL
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': file_key},
            ExpiresIn=3600  # 1 hour
        )
        
        response_text = f"Document accessibility issues have been fixed. Download the accessible Markdown file: {download_url}"
        
        return create_response(response_text, api_path)
        
    except Exception as e:
        logger.error(f"Error in fix lambda_handler: {str(e)}", exc_info=True)
        return create_response(f"Error fixing document: {str(e)}", event.get('apiPath', ''))



def extract_pdf_from_s3(s3_uri: str) -> str:
    """Extract text from PDF stored in S3"""
    s3 = boto3.client('s3')
    
    # Parse S3 URI
    bucket = s3_uri.replace('s3://', '').split('/')[0]
    key = '/'.join(s3_uri.replace('s3://', '').split('/')[1:])
    
    # Download PDF from S3
    response = s3.get_object(Bucket=bucket, Key=key)
    pdf_content = response['Body'].read()
    mime = response['ContentType']

    doc = fitz.open(stream=pdf_content, filetype=mime)
    markdown_text = pymupdf4llm.to_markdown(doc)
    return markdown_text
    
    
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
                    'body': json.dumps({'result': content})
                }
            }
        }
    }
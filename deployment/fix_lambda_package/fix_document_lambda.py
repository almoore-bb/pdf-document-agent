import json
import boto3
import base64
import uuid
from typing import Dict, Any
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to fix document accessibility issues using Bedrock
    """
    try:
        # Parse the event from Bedrock Agent
        api_path = event.get('apiPath', '')
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
        
        # Initialize AWS clients
        bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
        s3 = boto3.client('s3')
        
        # Decode document content
        try:
            decoded_content = base64.b64decode(document_content).decode('utf-8')
        except:
            decoded_content = document_content
        
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
        6. Set the document language field of the PDF if not already set.
        
        Return the original content with all accessibility issues corrected according to WCAG guidelines.
        """
        
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
        
        result = json.loads(response['body'].read())
        fixed_content = result['content'][0]['text']
        
        # Generate accessible PDF
        pdf_buffer = create_accessible_pdf(fixed_content)
        
        # Upload to S3
        bucket_name = 'ally-kb-supplemental-storage'
        file_key = f'fixed-documents/{uuid.uuid4()}.pdf'
        
        s3.put_object(
            Bucket=bucket_name,
            Key=file_key,
            Body=pdf_buffer.getvalue(),
            ContentType='application/pdf',
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
        
        response_text = f"Document accessibility issues have been fixed. Download the accessible PDF: {download_url}"
        
        return create_response(response_text, api_path)
        
    except Exception as e:
        return create_response(f"Error fixing document: {str(e)}", event.get('apiPath', ''))

def create_accessible_pdf(content: str) -> io.BytesIO:
    """Create an accessible PDF from the fixed content"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Create accessible styles
    title_style = ParagraphStyle(
        'AccessibleTitle',
        parent=styles['Title'],
        fontSize=18,
        spaceAfter=12,
        textColor='black'
    )
    
    heading_style = ParagraphStyle(
        'AccessibleHeading',
        parent=styles['Heading1'],
        fontSize=14,
        spaceAfter=8,
        textColor='black'
    )
    
    body_style = ParagraphStyle(
        'AccessibleBody',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=6,
        textColor='black',
        leading=14
    )
    
    story = []
    
    # Parse content and create structured PDF
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            story.append(Spacer(1, 6))
            continue
            
        if line.startswith('# '):
            story.append(Paragraph(line[2:], title_style))
        elif line.startswith('## '):
            story.append(Paragraph(line[3:], heading_style))
        elif line.startswith('### '):
            story.append(Paragraph(line[4:], heading_style))
        else:
            story.append(Paragraph(line, body_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

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
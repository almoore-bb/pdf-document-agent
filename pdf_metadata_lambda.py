import json
import boto3
import base64
import uuid
import logging
import fitz
import pymupdf4llm
from typing import Dict, Any
import io
import os
import urllib.request
import urllib.parse
from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import ServiceApiException, ServiceUsageException, SdkException
from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.autotag_pdf_job import AutotagPDFJob
from adobe.pdfservices.operation.pdfjobs.result.autotag_pdf_result import AutotagPDFResult

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients outside handler for reuse
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
s3 = boto3.client('s3')
sts = boto3.client('sts')

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to check and fix PDF metadata (title and language)
    """
    try:
        logger.info(f"PDF Metadata Lambda received event: {json.dumps(event, indent=2)}")
        
        api_path = event.get('apiPath', '')
        parameters = event.get('parameters', [])
        
        # Extract parameters
        pdf_uri = None
        user_title = None
        user_language = None
        
        for param in parameters:
            if param['name'] == 'pdf_s3_uri':
                pdf_uri = param['value']
            elif param['name'] == 'title':
                user_title = param['value']
            elif param['name'] == 'language':
                user_language = param['value']
        
        if not pdf_uri:
            return create_response("Error: No PDF URI provided", api_path)
        
        # Extract action parameter for consolidated endpoints
        action = None
        alt_text_data = None
        min_contrast_ratio = None
        summary_length = None
        for param in parameters:
            if param['name'] == 'action':
                action = param['value']
            elif param['name'] == 'alt_text_data':
                alt_text_data = param['value']
            elif param['name'] == 'min_contrast_ratio':
                min_contrast_ratio = param['value']
            elif param['name'] == 'summary_length':
                summary_length = param['value']
        
        if api_path == '/pdf-metadata':
            return handle_pdf_metadata(pdf_uri, action, user_title, user_language, api_path)
        elif api_path == '/pdf-tags':
            return handle_pdf_tags(pdf_uri, action, api_path)
        elif api_path == '/pdf-images':
            return handle_pdf_images(pdf_uri, action, alt_text_data, api_path)
        elif api_path == '/pdf-contrast':
            return handle_pdf_contrast(pdf_uri, action, min_contrast_ratio, api_path)
        elif api_path == '/pdf-summary':
            return generate_pdf_summary(pdf_uri, summary_length, api_path)
        else:
            return create_response(f"Unknown API path: {api_path}", api_path)
            
    except Exception as e:
        logger.error(f"Error in pdf metadata handler: {str(e)}", exc_info=True)
        return create_response(f"Error: {str(e)}", event.get('apiPath', ''))

def handle_pdf_metadata(pdf_uri: str, action: str, title: str, language: str, api_path: str) -> Dict[str, Any]:
    """Handle all PDF metadata operations based on action parameter"""
    if action == 'check':
        return check_pdf_metadata(pdf_uri, api_path)
    elif action == 'suggest-title':
        return suggest_title(pdf_uri, api_path)
    elif action == 'suggest-language':
        return suggest_language(pdf_uri, api_path)
    elif action == 'set-title':
        return set_pdf_title(pdf_uri, title, api_path)
    elif action == 'set-language':
        return set_pdf_language(pdf_uri, language, api_path)
    elif action == 'set-both':
        return set_both_metadata(pdf_uri, title, language, api_path)
    else:
        return create_response(f"Unknown metadata action: {action}", api_path)

def handle_pdf_tags(pdf_uri: str, action: str, api_path: str) -> Dict[str, Any]:
    """Handle PDF tagging operations based on action parameter"""
    if action == 'check':
        return check_pdf_tags(pdf_uri, api_path)
    elif action == 'add':
        return add_pdf_tags(pdf_uri, api_path)
    else:
        return create_response(f"Unknown tags action: {action}", api_path)

def handle_pdf_images(pdf_uri: str, action: str, alt_text_data: str, api_path: str) -> Dict[str, Any]:
    """Handle PDF image alt-text operations based on action parameter"""
    if action == 'check':
        return check_image_alt_text(pdf_uri, api_path)
    elif action == 'apply':
        return add_image_alt_text(pdf_uri, alt_text_data, api_path)
    else:
        return create_response(f"Unknown images action: {action}", api_path)

def handle_pdf_contrast(pdf_uri: str, action: str, min_contrast_ratio: str, api_path: str) -> Dict[str, Any]:
    """Handle PDF text contrast operations based on action parameter"""
    if action == 'check':
        return check_text_contrast(pdf_uri, min_contrast_ratio, api_path)
    elif action == 'fix':
        return fix_text_contrast(pdf_uri, min_contrast_ratio, api_path)
    else:
        return create_response(f"Unknown contrast action: {action}", api_path)

def check_pdf_metadata(pdf_uri: str, api_path: str) -> Dict[str, Any]:
    """Check if PDF has title and language metadata"""
    try:
        # Download PDF from S3 or URL
        pdf_content = download_pdf_content(pdf_uri)
        
        # Open PDF and check metadata
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        metadata = doc.metadata
        
        title = metadata.get('title', '').strip()
        
        # Check for language in PDF catalog
        language = ''
        try:
            catalog_xref = doc.pdf_catalog()
            lang_obj = doc.xref_get_key(catalog_xref, "Lang")
            if lang_obj:
                language = lang_obj.strip('()')
        except:
            pass
        
        doc.close()
        
        result = {
            'has_title': bool(title),
            'has_language': bool(language),
            'current_title': title,
            'current_language': language
        }
        
        return create_response(json.dumps(result), api_path)
        
    except Exception as e:
        logger.error(f"Error checking PDF metadata: {str(e)}")
        return create_response(f"Error checking metadata: {str(e)}", api_path)

def suggest_title(pdf_uri: str, api_path: str) -> Dict[str, Any]:
    """Extract content and suggest a title using enhanced LLM analysis"""
    try:
        # Extract strategic content from PDF
        extracted_data = extract_pdf_text_for_title(pdf_uri)
        data = json.loads(extracted_data)
        
        # Build enhanced prompt with multiple content sources
        prompt_parts = ["Analyze this document and suggest a concise, descriptive title (max 100 characters):"]
        
        if data['headers']:
            prompt_parts.append(f"\nLarge text/headers found: {', '.join(data['headers'][:3])}")
        
        prompt_parts.append(f"\nDocument content:\n{data['content']}")
        
        prompt_parts.append("\nConsider: 1) Existing headers/titles, 2) Main topic/purpose, 3) Document type. Return only the title.")
        
        prompt = '\n'.join(prompt_parts)
        
        streaming_response = bedrock.invoke_model_with_response_stream(
            modelId='global.anthropic.claude-sonnet-4-20250514-v1:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        suggested_title = ""
        stream = streaming_response.get('body')
        if not stream:
            raise ValueError("No response from Bedrock model")
        for evt in stream:
            if evt:
                chunk = json.loads(evt['chunk']['bytes'])
                if chunk['type'] == 'content_block_delta':
                    suggested_title += chunk['delta']['text']
        
        return create_response(f"Suggested title: {suggested_title.strip()}", api_path)
        
    except Exception as e:
        logger.error(f"Error suggesting title: {str(e)}")
        return create_response(f"Error suggesting title: {str(e)}", api_path)

def set_pdf_title(pdf_uri: str, title: str, api_path: str) -> Dict[str, Any]:
    """Set PDF title metadata and upload to S3"""
    try:
        if not title:
            return create_response("Error: No title provided", api_path)
        
        # Download PDF from S3 or URL
        pdf_content = download_pdf_content(pdf_uri)
        bucket = get_upload_bucket_from_uri(pdf_uri)
        
        # Open PDF and set title
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        metadata = doc.metadata
        metadata['title'] = title
        doc.set_metadata(metadata)
        
        # Save updated PDF
        updated_pdf = doc.tobytes()
        doc.close()
        
        # Upload to S3 with new key
        new_key = f"fixed-pdfs/{uuid.uuid4()}.pdf"
        s3.put_object(
            Bucket=bucket,
            Key=new_key,
            Body=updated_pdf,
            ContentType='application/pdf',
            Metadata={'title-fixed': 'true'}
        )
        
        new_s3_uri = f"s3://{bucket}/{new_key}"
        return create_response(f"Title set successfully. Updated PDF: {new_s3_uri}", api_path)
        
    except Exception as e:
        logger.error(f"Error setting title: {str(e)}")
        return create_response(f"Error setting title: {str(e)}", api_path)

def suggest_language(pdf_uri: str, api_path: str) -> Dict[str, Any]:
    """Extract content and suggest a language using LLM"""
    try:
        # Extract text from PDF
        content = extract_pdf_text(pdf_uri)
        
        prompt = f"""
        Based on the following document content, identify the primary language and return the ISO 639-1 language code (e.g., 'en' for English, 'es' for Spanish, 'fr' for French):
        
        {content[:2000]}
        
        Return only the two-letter language code, nothing else.
        """
        
        logger.info(f"Prompt for language suggestion: {prompt}")
        streaming_response = bedrock.invoke_model_with_response_stream(
            modelId='global.anthropic.claude-sonnet-4-20250514-v1:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        suggested_language = ""
        stream = streaming_response.get('body')
        if not stream:
            raise ValueError("No response from Bedrock model")
        for evt in stream:
            if evt:
                chunk = json.loads(evt['chunk']['bytes'])
                if chunk['type'] == 'content_block_delta':
                    suggested_language += chunk['delta']['text']
        
        return create_response(f"Suggested language: {suggested_language}", api_path)
        
    except Exception as e:
        logger.error(f"Error suggesting language: {str(e)}")
        return create_response(f"Error suggesting language: {str(e)}", api_path)

def set_pdf_language(pdf_uri: str, language: str, api_path: str) -> Dict[str, Any]:
    """Set PDF language metadata and upload to S3"""
    try:
        if not language:
            return create_response("Error: No language provided", api_path)
        
        # Download PDF from S3 or URL
        pdf_content = download_pdf_content(pdf_uri)
        bucket = get_upload_bucket_from_uri(pdf_uri)
        
        # Open PDF and set language in catalog while preserving title
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        
        # Preserve existing title metadata
        existing_metadata = doc.metadata
        
        # Set language in PDF catalog using proper method
        catalog_xref = doc.pdf_catalog()
        doc.xref_set_key(catalog_xref, "Lang", f"({language})")
        
        # Ensure title is preserved if it exists
        if existing_metadata.get('title'):
            doc.set_metadata(existing_metadata)
        
        # Save updated PDF
        updated_pdf = doc.tobytes()
        doc.close()
        
        # Upload to S3 with new key
        new_key = f"fixed-pdfs/{uuid.uuid4()}.pdf"
        s3.put_object(
            Bucket=bucket,
            Key=new_key,
            Body=updated_pdf,
            ContentType='application/pdf',
            Metadata={'language-fixed': 'true'}
        )
        
        # Generate presigned URL
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': new_key},
            ExpiresIn=3600
        )
        
        return create_response(f"Language set successfully. Download corrected PDF: {download_url}", api_path)
        
    except Exception as e:
        logger.error(f"Error setting language: {str(e)}")
        return create_response(f"Error setting language: {str(e)}", api_path)

def set_both_metadata(pdf_uri: str, title: str, language: str, api_path: str) -> Dict[str, Any]:
    """Set both PDF title and language metadata in one operation"""
    try:
        if not title or not language:
            return create_response("Error: Both title and language are required", api_path)
        
        # Download PDF from S3 or URL
        pdf_content = download_pdf_content(pdf_uri)
        bucket = get_upload_bucket_from_uri(pdf_uri)
        
        # Open PDF and check existing metadata
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        metadata = doc.metadata
        
        # Check existing title
        existing_title = metadata.get('title', '').strip()
        
        # Check existing language
        existing_language = ''
        try:
            catalog_xref = doc.pdf_catalog()
            lang_obj = doc.xref_get_key(catalog_xref, "Lang")
            if lang_obj:
                existing_language = lang_obj.strip('()')
        except:
            pass
        
        # Only set title if not already present
        if not existing_title:
            metadata['title'] = title
            doc.set_metadata(metadata)
        
        # Only set language if not already present
        if not existing_language:
            catalog_xref = doc.pdf_catalog()
            doc.xref_set_key(catalog_xref, "Lang", f"({language})")
        
        # Save updated PDF
        updated_pdf = doc.tobytes()
        doc.close()
        
        # Upload to S3 with new key
        new_key = f"fixed-pdfs/{uuid.uuid4()}.pdf"
        s3.put_object(
            Bucket=bucket,
            Key=new_key,
            Body=updated_pdf,
            ContentType='application/pdf',
            Metadata={
                'title-fixed': 'true',
                'language-fixed': 'true'
            }
        )
        
        # Generate presigned URL
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': new_key},
            ExpiresIn=3600
        )
        
        # Create response message based on what was set
        if not existing_title and not existing_language:
            message = "Title and language set successfully."
        elif not existing_title:
            message = "Title set successfully. Language was already present."
        elif not existing_language:
            message = "Language set successfully. Title was already present."
        else:
            message = "Both title and language were already present. No changes made."
        
        return create_response(f"{message} Download PDF: {download_url}", api_path)
        
    except Exception as e:
        logger.error(f"Error setting both metadata: {str(e)}")
        return create_response(f"Error setting both metadata: {str(e)}", api_path)

def check_pdf_tags(pdf_uri: str, api_path: str) -> Dict[str, Any]:
    """Check if PDF has structural tags"""
    try:
        # Download PDF from S3 or URL
        pdf_content = download_pdf_content(pdf_uri)
        
        # Open PDF and check for tags
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        
        # Check if PDF is tagged
        is_tagged = False
        try:
            catalog_xref = doc.pdf_catalog()
            struct_tree_root = doc.xref_get_key(catalog_xref, "StructTreeRoot")
            is_tagged = bool(struct_tree_root)
        except:
            pass
        
        doc.close()
        
        result = {
            'has_tags': is_tagged,
            'message': 'PDF has structural tags' if is_tagged else 'PDF is missing structural tags'
        }
        
        return create_response(json.dumps(result), api_path)
        
    except Exception as e:
        logger.error(f"Error checking PDF tags: {str(e)}")
        return create_response(f"Error checking tags: {str(e)}", api_path)

def add_pdf_tags(pdf_uri: str, api_path: str) -> Dict[str, Any]:
    """Add advanced structural tags to PDF using Adobe PDF Services"""
    try:
        # Download PDF from S3 or URL
        pdf_content = download_pdf_content(pdf_uri)
        bucket = get_upload_bucket_from_uri(pdf_uri)
        
        
        # Use Adobe PDF Services for advanced tagging
        client_id = os.environ.get('PDF_SERVICES_CLIENT_ID')
        client_secret = os.environ.get('PDF_SERVICES_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            logger.warning("Adobe PDF Services credentials not found, falling back to basic tagging")
            return add_basic_pdf_tags(pdf_uri, api_path)
        
        # Create credentials
        credentials = ServicePrincipalCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
        
        # Create PDF Services instance
        pdf_services = PDFServices(credentials=credentials)
        
        # Create asset from PDF content
        input_asset = pdf_services.upload(input_stream=io.BytesIO(pdf_content), mime_type=PDFServicesMediaType.PDF)
        
        # Create AutoTag job
        autotag_pdf_job = AutotagPDFJob(input_asset=input_asset)
        
        # Submit job and get result
        location = pdf_services.submit(autotag_pdf_job)
        pdf_services_response = pdf_services.get_job_result(location, AutotagPDFResult)
        
        # Get the tagged PDF
        result_asset = pdf_services_response.get_result().get_tagged_pdf()
        stream_asset = pdf_services.get_content(result_asset)
        
        # Read the tagged PDF content
        tagged_pdf_content = stream_asset.get_input_stream()
        
        # Upload to S3 with new key
        new_key = f"fixed-pdfs/{uuid.uuid4()}.pdf"
        s3.put_object(
            Bucket=bucket,
            Key=new_key,
            Body=tagged_pdf_content,
            ContentType='application/pdf',
            Metadata={'tags-added': 'true', 'adobe-services': 'true'}
        )
        
        # Generate presigned URL
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': new_key},
            ExpiresIn=3600
        )
        
        return create_response(f"Advanced structural tags added successfully using Adobe PDF Services. Download tagged PDF: {download_url}", api_path)
        
    except (ServiceApiException, ServiceUsageException, SdkException) as e:
        logger.error(f"Adobe PDF Services error: {str(e)}")
        # Fall back to basic tagging
        return add_basic_pdf_tags(pdf_uri, api_path)
    except Exception as e:
        logger.error(f"Error adding PDF tags: {str(e)}")
        return create_response(f"Error adding tags: {str(e)}", api_path)

def add_basic_pdf_tags(pdf_uri: str, api_path: str) -> Dict[str, Any]:
    """Add basic structural tags to PDF using PyMuPDF (fallback method)"""
    try:
        # Download PDF from S3 or URL
        pdf_content = download_pdf_content(pdf_uri)
        bucket = get_upload_bucket_from_uri(pdf_uri)
        
        # Open PDF and add basic tagging structure
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        
        # Add basic structure tree root
        struct_tree_dict = {
            "Type": "/StructTreeRoot",
            "K": [],
            "ParentTree": {"Nums": []}
        }
        
        # Create structure tree root object
        struct_tree_xref = doc.new_object(struct_tree_dict)
        
        # Add StructTreeRoot to catalog
        catalog_xref = doc.pdf_catalog()
        doc.xref_set_key(catalog_xref, "StructTreeRoot", f"{struct_tree_xref} 0 R")
        
        # Mark PDF as tagged
        doc.xref_set_key(catalog_xref, "MarkInfo", "{/Marked true}")
        
        # Save updated PDF
        updated_pdf = doc.tobytes()
        doc.close()
        
        # Upload to S3 with new key
        new_key = f"fixed-pdfs/{uuid.uuid4()}.pdf"
        s3.put_object(
            Bucket=bucket,
            Key=new_key,
            Body=updated_pdf,
            ContentType='application/pdf',
            Metadata={'tags-added': 'true', 'basic-tags': 'true'}
        )
        
        # Generate presigned URL
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': new_key},
            ExpiresIn=3600
        )
        
        return create_response(f"Basic structural tags added successfully. Download tagged PDF: {download_url}", api_path)
        
    except Exception as e:
        logger.error(f"Error adding basic PDF tags: {str(e)}")
        return create_response(f"Error adding basic tags: {str(e)}", api_path)

def check_image_alt_text(pdf_uri: str, api_path: str) -> Dict[str, Any]:
    """Check PDF images for alt-text and suggest alt-text for missing ones"""
    try:
        pdf_content = download_pdf_content(pdf_uri)
        
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        all_images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                
                # Check if image already has alt-text
                has_alt_text = False
                try:
                    img_obj = doc.xref_get_key(xref, "Alt")
                    has_alt_text = bool(img_obj and img_obj.strip())
                except:
                    pass
                
                image_info = {
                    'image_id': f"page_{page_num + 1}_img_{img_index}",
                    'page': page_num + 1,
                    'image_index': img_index,
                    'xref': xref,
                    'has_alt_text': has_alt_text,
                    'current_alt_text': img_obj.strip('()') if has_alt_text else None
                }
                
                # Generate suggestion only if no alt-text exists
                if not has_alt_text:
                    try:
                        pix = fitz.Pixmap(doc, xref)
                        if pix.n - pix.alpha < 4:  # RGB/CMYK only
                            img_data = pix.tobytes("png")
                            alt_text = generate_alt_text_suggestion(img_data)
                            image_info['suggested_alt_text'] = alt_text
                        pix = None
                    except:
                        image_info['suggested_alt_text'] = "Image"
                
                all_images.append(image_info)
        
        doc.close()
        
        if not all_images:
            return create_response("No images found in PDF", api_path)
        
        images_needing_alt = [img for img in all_images if not img['has_alt_text']]
        
        result = {
            'total_images': len(all_images),
            'images_with_alt_text': len(all_images) - len(images_needing_alt),
            'images_needing_alt_text': len(images_needing_alt),
            'images': all_images
        }
        
        return create_response(json.dumps(result), api_path)
        
    except Exception as e:
        logger.error(f"Error checking image alt-text: {str(e)}")
        return create_response(f"Error checking image alt-text: {str(e)}", api_path)

def add_image_alt_text(pdf_uri: str, alt_text_data: str, api_path: str) -> Dict[str, Any]:
    """Add alt-text to PDF images using image IDs"""
    try:
        if not alt_text_data:
            return create_response("Error: No alt-text data provided", api_path)
        
        # Parse alt-text data: {"image_id": "alt_text", ...}
        alt_text_map = json.loads(alt_text_data)
        
        pdf_content = download_pdf_content(pdf_uri)
        bucket = get_upload_bucket_from_uri(pdf_uri)
        
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        applied_count = 0
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                image_id = f"page_{page_num + 1}_img_{img_index}"
                
                if image_id in alt_text_map:
                    xref = img[0]
                    alt_text = alt_text_map[image_id]
                    
                    try:
                        # Set alt-text in PDF structure
                        doc.xref_set_key(xref, "Alt", f"({alt_text})")
                        applied_count += 1
                        logger.info(f"Applied alt-text to {image_id}: {alt_text}")
                    except Exception as e:
                        logger.error(f"Failed to set alt-text for {image_id}: {str(e)}")
        
        updated_pdf = doc.tobytes()
        doc.close()
        
        # Upload to S3 with new key
        new_key = f"fixed-pdfs/{uuid.uuid4()}.pdf"
        s3.put_object(
            Bucket=bucket,
            Key=new_key,
            Body=updated_pdf,
            ContentType='application/pdf',
            Metadata={'alt-text-added': 'true'}
        )
        
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': new_key},
            ExpiresIn=3600
        )
        
        return create_response(f"Alt-text applied to {applied_count} images. Download PDF: {download_url}", api_path)
        
    except Exception as e:
        logger.error(f"Error adding image alt-text: {str(e)}")
        return create_response(f"Error adding image alt-text: {str(e)}", api_path)

def generate_alt_text_suggestion(image_data: bytes) -> str:
    """Generate alt-text suggestion for image using Bedrock"""
    try:
        # Encode image to base64
        import base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        prompt = "Describe this image in a concise way suitable for alt-text (maximum 125 characters):"
        
        streaming_response = bedrock.invoke_model_with_response_stream(
            modelId='global.anthropic.claude-sonnet-4-20250514-v1:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 50,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_base64}}
                    ]
                }]
            })
        )
        
        alt_text = ""
        stream = streaming_response.get('body')
        if stream:
            for evt in stream:
                if evt:
                    chunk = json.loads(evt['chunk']['bytes'])
                    if chunk['type'] == 'content_block_delta':
                        alt_text += chunk['delta']['text']
        
        return alt_text.strip() or "Image"
        
    except Exception as e:
        logger.error(f"Error generating alt-text: {str(e)}")
        return "Image"

def download_pdf_content(pdf_uri: str) -> bytes:
    """Download PDF content from S3 URI or regular URL"""
    try:
        if pdf_uri.startswith('s3://'):
            # Handle S3 URI
            bucket, key = parse_s3_uri(pdf_uri)
            response = s3.get_object(Bucket=bucket, Key=key)
            return response['Body'].read()
        elif pdf_uri.startswith(('http://', 'https://')):
            # Handle regular URL
            with urllib.request.urlopen(pdf_uri) as response:
                return response.read()
        else:
            raise ValueError(f"Unsupported URI format: {pdf_uri}. Must be S3 URI (s3://) or HTTP/HTTPS URL")
    except Exception as e:
        logger.error(f"Error downloading PDF from {pdf_uri}: {str(e)}")
        raise

def extract_pdf_text_for_title(pdf_uri: str) -> str:
    """Extract strategic text from PDF for title suggestion"""
    try:
        pdf_content = download_pdf_content(pdf_uri)
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        
        # Strategy 1: Look for existing title in large fonts on first page
        first_page = doc[0]
        blocks = first_page.get_text("dict")
        title_candidates = []
        
        for block in blocks.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        font_size = span.get("size", 0)
                        if text and font_size > 14:  # Large font likely title
                            title_candidates.append((text, font_size))
        
        # Strategy 2: Get first 3 pages content
        content_parts = []
        max_pages = min(3, len(doc))
        
        for page_num in range(max_pages):
            page_text = doc[page_num].get_text()
            # Take first 800 chars per page
            content_parts.append(page_text[:800])
        
        # Strategy 3: Look for headers/headings patterns
        headers = []
        for candidate, size in sorted(title_candidates, key=lambda x: x[1], reverse=True)[:3]:
            if len(candidate) > 5 and len(candidate) < 100:
                headers.append(candidate)
        
        doc.close()
        
        # Combine strategies
        result = {
            'headers': headers,
            'content': ' '.join(content_parts)[:2000]
        }
        
        return json.dumps(result)
        
    except Exception as e:
        logger.error(f"Error extracting PDF text for title: {str(e)}")
        raise

def extract_pdf_text(pdf_uri: str) -> str:
    """Extract text from first page of PDF (legacy function)"""
    try:
        pdf_content = download_pdf_content(pdf_uri)
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        first_page = doc[0]
        text = first_page.get_text()
        doc.close()
        return text
    except Exception as e:
        logger.error(f"Error extracting PDF text: {str(e)}")
        raise

def parse_s3_uri(s3_uri: str) -> tuple:
    """Parse S3 URI into bucket and key"""
    parts = s3_uri.replace('s3://', '').split('/', 1)
    return parts[0], parts[1]

def get_upload_bucket_from_uri(pdf_uri: str) -> str:
    """Get the appropriate S3 bucket for uploading fixed PDFs"""
    if pdf_uri.startswith('s3://'):
        # Use the same bucket as the source
        bucket, _ = parse_s3_uri(pdf_uri)
        return bucket
    else:
        # Use default bucket for URL sources
        return 'ally-lambda-outputs'

def check_text_contrast(pdf_uri: str, min_contrast_ratio: str, api_path: str) -> Dict[str, Any]:
    """Check text contrast ratios in PDF"""
    try:
        pdf_content = download_pdf_content(pdf_uri)
        
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        contrast_issues = []
        
        # Default contrast ratios per WCAG guidelines
        min_ratio = float(min_contrast_ratio) if min_contrast_ratio else 4.5
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Get text blocks with formatting info
            blocks = page.get_text("dict")
            
            for block in blocks.get("blocks", []):
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                # Get text color (RGB)
                                color = span.get("color", 0)  # Default black
                                font_size = span.get("size", 12)
                                
                                # Convert color integer to RGB
                                text_color = {
                                    'r': (color >> 16) & 0xFF,
                                    'g': (color >> 8) & 0xFF,
                                    'b': color & 0xFF
                                }
                                
                                # Assume white background for now (common case)
                                bg_color = {'r': 255, 'g': 255, 'b': 255}
                                
                                # Calculate contrast ratio
                                contrast_ratio = calculate_contrast_ratio(text_color, bg_color)
                                
                                # Check if contrast meets requirements
                                required_ratio = 3.0 if font_size >= 18 else min_ratio
                                
                                if contrast_ratio < required_ratio:
                                    contrast_issues.append({
                                        'page': page_num + 1,
                                        'text': text[:50] + '...' if len(text) > 50 else text,
                                        'font_size': font_size,
                                        'text_color': text_color,
                                        'background_color': bg_color,
                                        'contrast_ratio': round(contrast_ratio, 2),
                                        'required_ratio': required_ratio,
                                        'bbox': span.get('bbox', [])
                                    })
        
        doc.close()
        
        if not contrast_issues:
            return create_response("All text meets WCAG contrast requirements", api_path)
        
        result = {
            'issues_count': len(contrast_issues),
            'contrast_issues': contrast_issues[:20]  # Limit to first 20 issues
        }
        
        return create_response(json.dumps(result), api_path)
        
    except Exception as e:
        logger.error(f"Error checking text contrast: {str(e)}")
        return create_response(f"Error checking text contrast: {str(e)}", api_path)

def fix_text_contrast(pdf_uri: str, min_contrast_ratio: str, api_path: str) -> Dict[str, Any]:
    """Fix text contrast issues in PDF including tables and other objects"""
    try:
        pdf_content = download_pdf_content(pdf_uri)
        bucket = get_upload_bucket_from_uri(pdf_uri)
        
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        fixes_applied = 0
        min_ratio = float(min_contrast_ratio) if min_contrast_ratio else 4.5
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Get all drawings (rectangles, tables, etc.) to detect backgrounds
            drawings = page.get_drawings()
            table_areas = []
            
            # Identify table/background areas
            for drawing in drawings:
                for item in drawing.get("items", []):
                    if item[0] == "re":  # Rectangle
                        rect = fitz.Rect(item[1])
                        fill_color = drawing.get("fill", None)
                        if fill_color:
                            table_areas.append({
                                'rect': rect,
                                'color': fill_color
                            })
            
            # Get text blocks
            blocks = page.get_text("dict")
            
            for block in blocks.get("blocks", []):
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                color = span.get("color", 0)
                                font_size = span.get("size", 12)
                                bbox = span.get("bbox", [])
                                
                                if not bbox:
                                    continue
                                    
                                text_rect = fitz.Rect(bbox)
                                
                                # Convert text color to RGB
                                text_color = {
                                    'r': (color >> 16) & 0xFF,
                                    'g': (color >> 8) & 0xFF,
                                    'b': color & 0xFF
                                }
                                
                                # Detect background color from table areas or default to white
                                bg_color = {'r': 255, 'g': 255, 'b': 255}
                                for area in table_areas:
                                    if area['rect'].intersects(text_rect):
                                        # Convert fill color to RGB
                                        fill = area['color']
                                        if isinstance(fill, (list, tuple)) and len(fill) >= 3:
                                            bg_color = {
                                                'r': int(fill[0] * 255),
                                                'g': int(fill[1] * 255),
                                                'b': int(fill[2] * 255)
                                            }
                                        break
                                
                                contrast_ratio = calculate_contrast_ratio(text_color, bg_color)
                                required_ratio = 3.0 if font_size >= 18 else min_ratio
                                
                                if contrast_ratio < required_ratio:
                                    # Fix by adjusting text color for better contrast
                                    new_color = get_accessible_color(bg_color, required_ratio)
                                    
                                    # Remove old text
                                    page.add_redact_annot(text_rect)
                                    page.apply_redactions()
                                    
                                    # Add new text with better contrast
                                    page.insert_text(
                                        (text_rect.x0, text_rect.y1 - 2),
                                        text,
                                        fontsize=font_size,
                                        color=(new_color['r']/255, new_color['g']/255, new_color['b']/255)
                                    )
                                    
                                    fixes_applied += 1
        
        # Save updated PDF
        updated_pdf = doc.tobytes()
        doc.close()
        
        # Upload to S3 with new key
        new_key = f"fixed-pdfs/{uuid.uuid4()}.pdf"
        s3.put_object(
            Bucket=bucket,
            Key=new_key,
            Body=updated_pdf,
            ContentType='application/pdf',
            Metadata={'contrast-fixed': 'true'}
        )
        
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': new_key},
            ExpiresIn=3600
        )
        
        return create_response(f"Fixed {fixes_applied} contrast issues. Download PDF: {download_url}", api_path)
        
    except Exception as e:
        logger.error(f"Error fixing text contrast: {str(e)}")
        return create_response(f"Error fixing text contrast: {str(e)}", api_path)

def calculate_contrast_ratio(color1: dict, color2: dict) -> float:
    """Calculate WCAG contrast ratio between two colors"""
    def get_luminance(color):
        """Calculate relative luminance of a color"""
        def linearize(c):
            c = c / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        
        r = linearize(color['r'])
        g = linearize(color['g'])
        b = linearize(color['b'])
        
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    
    l1 = get_luminance(color1)
    l2 = get_luminance(color2)
    
    # Ensure l1 is the lighter color
    if l1 < l2:
        l1, l2 = l2, l1
    
    return (l1 + 0.05) / (l2 + 0.05)

def get_accessible_color(bg_color: dict, target_ratio: float) -> dict:
    """Get a text color that meets the target contrast ratio against background"""
    # For white background, make text darker
    if bg_color['r'] > 200 and bg_color['g'] > 200 and bg_color['b'] > 200:
        # Calculate how dark the text needs to be
        # Start with black and adjust if needed
        test_color = {'r': 0, 'g': 0, 'b': 0}
        ratio = calculate_contrast_ratio(test_color, bg_color)
        
        if ratio >= target_ratio:
            return test_color
        
        # If pure black doesn't work, try dark gray
        for darkness in range(0, 128, 10):
            test_color = {'r': darkness, 'g': darkness, 'b': darkness}
            ratio = calculate_contrast_ratio(test_color, bg_color)
            if ratio >= target_ratio:
                return test_color
    
    # Default to black
    return {'r': 0, 'g': 0, 'b': 0}

def generate_pdf_summary(pdf_uri: str, summary_length: str, api_path: str) -> Dict[str, Any]:
    """Generate a comprehensive summary of PDF document content"""
    try:
        pdf_content = download_pdf_content(pdf_uri)
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        
        # Extract text from all pages with structure
        full_text = ""
        page_count = len(doc)
        
        # Extract text using pymupdf4llm for better structure
        md_text = pymupdf4llm.to_markdown(doc)
        
        # Also get plain text for fallback
        for page_num in range(min(10, page_count)):  # Limit to first 10 pages for performance
            page = doc[page_num]
            page_text = page.get_text()
            full_text += f"\n\nPage {page_num + 1}:\n{page_text}"
        
        doc.close()
        
        # Use structured markdown if available, otherwise plain text
        content_to_analyze = md_text if md_text.strip() else full_text
        
        # Truncate content to fit model limits (keep most relevant parts)
        max_chars = 15000
        if len(content_to_analyze) > max_chars:
            # Take beginning and end portions
            start_portion = content_to_analyze[:max_chars//2]
            end_portion = content_to_analyze[-(max_chars//2):]
            content_to_analyze = start_portion + "\n\n[... content truncated ...]\n\n" + end_portion
        
        # Configure summary based on length parameter
        length_config = {
            'brief': {
                'max_tokens': 150,
                'instruction': 'Provide a brief 2-3 sentence summary highlighting the main topic and key points.'
            },
            'detailed': {
                'max_tokens': 400,
                'instruction': 'Provide a detailed 1-2 paragraph summary covering the main topics, key findings, and important details.'
            },
            'comprehensive': {
                'max_tokens': 800,
                'instruction': 'Provide a comprehensive analysis including main topics, key findings, methodology (if applicable), conclusions, and significant details.'
            }
        }
        
        config = length_config.get(summary_length, length_config['detailed'])
        
        prompt = f"""
        Analyze the following document and {config['instruction']}
        
        Document ({page_count} pages):
        {content_to_analyze}
        
        Focus on:
        - Main topic and purpose
        - Key findings or conclusions
        - Important data or statistics
        - Methodology (if research/technical document)
        - Recommendations or next steps
        
        Provide a clear, well-structured summary:
        """
        
        streaming_response = bedrock.invoke_model_with_response_stream(
            modelId='global.anthropic.claude-sonnet-4-20250514-v1:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": config['max_tokens'],
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        summary = ""
        stream = streaming_response.get('body')
        if not stream:
            raise ValueError("No response from Bedrock model")
        
        for evt in stream:
            if evt:
                chunk = json.loads(evt['chunk']['bytes'])
                if chunk['type'] == 'content_block_delta':
                    summary += chunk['delta']['text']
        
        # Add document metadata to summary
        result = {
            'summary': summary.strip(),
            'document_info': {
                'total_pages': page_count,
                'summary_type': summary_length or 'detailed'
            }
        }
        
        return create_response(json.dumps(result), api_path)
        
    except Exception as e:
        logger.error(f"Error generating PDF summary: {str(e)}")
        return create_response(f"Error generating summary: {str(e)}", api_path)

def create_response(content: str, api_path: str) -> Dict[str, Any]:
    """Create properly formatted response for Bedrock Agent"""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': 'PDFMetadataGroup',
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
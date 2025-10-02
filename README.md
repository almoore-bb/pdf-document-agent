# PDF Document Agent

An AI-powered AWS Bedrock agent for PDF accessibility analysis and remediation. This agent helps identify and fix accessibility issues in PDF documents to ensure WCAG compliance.

## Features

- **PDF Metadata Management**: Check, suggest, and set PDF title and language metadata
- **Structural Tagging**: Add accessibility tags to PDFs using Adobe PDF Services or PyMuPDF
- **Image Alt-Text**: Detect images missing alt-text and generate AI-powered suggestions
- **Text Contrast Analysis**: Check and fix text contrast issues for WCAG compliance
- **Document Summarization**: Generate concise or comprehensive PDF summaries
- **Flexible Input**: Supports both S3 URIs and HTTP/HTTPS URLs

## Architecture

- **AWS Bedrock Agent**: Orchestrates accessibility operations
- **Lambda Functions**: Process PDF documents and apply fixes
- **Claude Sonnet 4**: Provides AI-powered analysis and suggestions
- **Adobe PDF Services**: Advanced PDF tagging capabilities
- **PyMuPDF**: PDF processing and manipulation

## Prerequisites

- AWS CLI configured with appropriate permissions
- Terraform >= 1.2.0
- Python 3.13
- Adobe PDF Services credentials (stored in AWS Parameter Store)

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/almoore-bb/pdf-document-agent.git
   cd pdf-document-agent
   ```

2. **Configure Adobe PDF Services** (optional)
   ```bash
   aws ssm put-parameter --name "/application/auto-tagging/adobe/configuration/client-id-andrew" --value "your-client-id" --type "String"
   aws ssm put-parameter --name "/application/auto-tagging/adobe/configuration/client-secret-andrew" --value "your-client-secret" --type "SecureString"
   ```

3. **Deploy the agent**
   ```bash
   cd deployment
   ./deploy.sh "my-pdf-agent" "PDFHelper"
   ```

## API Operations

### PDF Metadata (`/pdf-metadata`)
- `check`: Check existing title and language metadata
- `suggest-title`: AI-generated title suggestions
- `suggest-language`: AI-detected language
- `set-title`: Set PDF title
- `set-language`: Set PDF language
- `set-both`: Set both title and language

### PDF Tagging (`/pdf-tags`)
- `check`: Check for structural accessibility tags
- `add`: Add structural tags using Adobe PDF Services or PyMuPDF

### Image Alt-Text (`/pdf-images`)
- `check`: Find images and suggest alt-text for missing ones
- `apply`: Apply alt-text to specific images using image IDs

### Text Contrast (`/pdf-contrast`)
- `check`: Analyze text contrast ratios against WCAG standards
- `fix`: Automatically fix low-contrast text

### Document Summary (`/pdf-summary`)
- Generate summaries with configurable length: `brief`, `detailed`, `comprehensive`

## Usage Examples

```bash
# Check PDF metadata
curl -X POST "https://your-agent-endpoint/pdf-metadata" \
  -d "pdf_s3_uri=s3://bucket/document.pdf&action=check"

# Generate document summary
curl -X POST "https://your-agent-endpoint/pdf-summary" \
  -d "pdf_s3_uri=https://example.com/report.pdf&summary_length=detailed"

# Check and fix text contrast
curl -X POST "https://your-agent-endpoint/pdf-contrast" \
  -d "pdf_s3_uri=s3://bucket/document.pdf&action=fix&min_contrast_ratio=4.5"
```

## Configuration

### Environment Variables
- `PDF_SERVICES_CLIENT_ID`: Adobe PDF Services client ID
- `PDF_SERVICES_CLIENT_SECRET`: Adobe PDF Services client secret

### Terraform Variables
- `agent_name`: Name of the Bedrock agent (default: "ally-document-agent")
- `agent_alias_name`: Alias name for the agent (default: "Samantha")
- `action_group_state`: State of action groups (default: "ENABLED")

## File Structure

```
├── deployment/
│   ├── main.tf              # Terraform infrastructure
│   ├── vars.tf              # Terraform variables
│   ├── deploy.sh            # Deployment script
│   └── destroy.sh           # Cleanup script
├── lambda_function.py       # Document analyzer Lambda
├── fix_document_lambda.py   # Document fixer Lambda
├── pdf_metadata_lambda.py   # PDF metadata operations Lambda
├── router_lambda.py         # Request router Lambda
├── action_group_schema.json # API schema for document operations
└── pdf_metadata_schema.json # API schema for PDF metadata operations
```

## Development

### Local Testing
```bash
# Test Lambda functions locally
python3 -m pytest tests/

# Validate Terraform configuration
cd deployment
terraform validate
terraform plan
```

### Adding New Features
1. Update the appropriate Lambda function
2. Modify the OpenAPI schema if needed
3. Test locally
4. Deploy using `./deploy.sh`

## Troubleshooting

### Common Issues
- **Layer creation fails**: Ensure Docker is running for ARM64 compilation
- **Adobe PDF Services errors**: Verify credentials in Parameter Store
- **Bedrock model access**: Ensure proper IAM permissions for Claude Sonnet 4

### Logs
Check CloudWatch logs for each Lambda function:
- `/aws/lambda/ally-document-analyzer`
- `/aws/lambda/ally-pdf-metadata`
- `/aws/lambda/ally-document-fixer`
- `/aws/lambda/ally-router`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
- Create an issue in this repository
- Check the troubleshooting section
- Review CloudWatch logs for error details

## Example Usage
<video controls src="https://anthologyinc-my.sharepoint.com/:v:/r/personal/andrew_moore_anthology_com/Documents/example-remediation.mov?csf=1&web=1&nav=eyJyZWZlcnJhbEluZm8iOnsicmVmZXJyYWxBcHAiOiJPbmVEcml2ZUZvckJ1c2luZXNzIiwicmVmZXJyYWxBcHBQbGF0Zm9ybSI6IldlYiIsInJlZmVycmFsTW9kZSI6InZpZXciLCJyZWZlcnJhbFZpZXciOiJNeUZpbGVzTGlua0NvcHkifX0&e=SdD9qb" title="AI-Enabled PDF Remediation with Bedrock"></video>
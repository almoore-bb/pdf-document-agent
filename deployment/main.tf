terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.90"
    }
    
  }

  required_version = ">= 1.2.0"
}

provider "aws" {
  region = "us-east-1"
  profile = "performance"
}



# Get current AWS account ID and region
data "aws_caller_identity" "current" {}

# S3 bucket for Lambda processed files
resource "aws_s3_bucket" "lambda_outputs" {
  bucket = "ally-lambda-outputs"

  tags = {
    Name = "Ally Lambda Outputs"
    Env = "Dev"
  }
}

# Retrieve PDF Services credentials from Parameter Store
data "aws_ssm_parameter" "pdf_services_client_id" {
  name = "/application/auto-tagging/adobe/configuration/client-id-andrew"
}

data "aws_ssm_parameter" "pdf_services_client_secret" {
  name            = "/application/auto-tagging/adobe/configuration/client-secret-andrew"
  with_decryption = true
}
data "aws_region" "current" {}





# Let's configure our Bedrock agent

# Create the IAM role for the Bedrock Agent
data "aws_iam_policy_document" "agent_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "bedrock_agent_role" {
  name_prefix        = "bedrock-agent-"
  assume_role_policy = data.aws_iam_policy_document.agent_assume_role.json
}

# Create policy for the agent
data "aws_iam_policy_document" "agent_policy" {
  statement {
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket"
    ]
    resources = [
      "arn:aws:s3:::document-agent-uploads/*",
      "arn:aws:s3:::document-agent-uploads"
    ]
  }
  # Add code interpreter permissions
  statement {
    effect = "Allow"
    actions = [
      "bedrock:InvokeAgent",
      "bedrock:GetAgent",
      "bedrock:ListAgents"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "agent_policy" {
  name   = "bedrock-agent-policy"
  role   = aws_iam_role.bedrock_agent_role.id
  policy = data.aws_iam_policy_document.agent_policy.json
}

# Create the Bedrock Agent
resource "aws_bedrockagent_agent" "ally_agent" {
  agent_name                  = var.agent_name
  agent_resource_role_arn     = aws_iam_role.bedrock_agent_role.arn
  foundation_model            = "anthropic.claude-3-5-sonnet-20240620-v1:0"
  instruction                 = file("${path.module}/prompt.txt")
  description                 = "AI assistant for web accessibility guidelines and WCAG compliance"


}




# Lambda function for document analysis
resource "aws_iam_role" "lambda_role" {
  name_prefix = "ally-lambda-role-"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "ally-lambda-policy"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "lambda:InvokeFunction",
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Resource = [
          "*",
          "arn:aws:s3:::document-agent-uploads/*",
          "arn:aws:s3:::document-agent-uploads",
          "arn:aws:s3:::ally-lambda-outputs/*",
          "arn:aws:s3:::ally-lambda-outputs"
        ]
      }
    ]
  })
}





# Create PyMuPDF layer
resource "null_resource" "create_pymupdf_layer" {
  provisioner "local-exec" {
    command = <<EOF
      mkdir -p ${path.module}/pymupdf_layer/python
      python3 -m pip install pymupdf pymupdf4llm --target ${path.module}/pymupdf_layer/python --platform manylinux2014_aarch64 --only-binary=:all:
      cd ${path.module}/pymupdf_layer && zip -r ../pymupdf_layer.zip python/
    EOF
  }
  triggers = {
    always_run = timestamp()
  }
}

# Create Adobe PDF Services layer
resource "null_resource" "create_adobe_layer" {
  provisioner "local-exec" {
    command = <<EOF
      mkdir -p ${path.module}/adobe_layer/python
      python3 -m pip install pdfservices-sdk --target ${path.module}/adobe_layer/python --platform manylinux2014_aarch64 --only-binary=:all:
      cd ${path.module}/adobe_layer && zip -r ../adobe_layer.zip python/
    EOF
  }
  triggers = {
    always_run = timestamp()
  }
}

resource "aws_lambda_layer_version" "pymupdf" {
  filename         = "${path.module}/pymupdf_layer.zip"
  layer_name       = "ally-pymupdf"
  compatible_runtimes = ["python3.13"]
  compatible_architectures = ["arm64"]
  depends_on       = [null_resource.create_pymupdf_layer]
}

resource "aws_lambda_layer_version" "adobe_pdf_services" {
  filename         = "${path.module}/adobe_layer.zip"
  layer_name       = "ally-adobe-pdf-services"
  compatible_runtimes = ["python3.13"]
  compatible_architectures = ["arm64"]
  depends_on       = [null_resource.create_adobe_layer]
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambda_function.py"
  output_path = "${path.module}/lambda_function.zip"
}

data "archive_file" "fix_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../fix_document_lambda.py"
  output_path = "${path.module}/fix_document_lambda.zip"
}

data "archive_file" "router_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../router_lambda.py"
  output_path = "${path.module}/router_lambda.zip"
}

data "archive_file" "pdf_metadata_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../pdf_metadata_lambda.py"
  output_path = "${path.module}/pdf_metadata_lambda.zip"
}

resource "aws_lambda_function" "document_analyzer" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "ally-document-analyzer"
  role            = aws_iam_role.lambda_role.arn
  handler         = "lambda_function.lambda_handler"
  runtime         = "python3.13"
  architectures    = ["arm64"]
  timeout         = 900
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.pymupdf.arn]
  depends_on       = [aws_lambda_layer_version.pymupdf]
}

resource "aws_lambda_function" "document_fixer" {
  filename         = data.archive_file.fix_lambda_zip.output_path
  function_name    = "ally-document-fixer"
  role            = aws_iam_role.lambda_role.arn
  handler         = "fix_document_lambda.lambda_handler"
  runtime         = "python3.13"
  architectures    = ["arm64"] 
  timeout         = 900
  source_code_hash = data.archive_file.fix_lambda_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.pymupdf.arn]
  depends_on       = [aws_lambda_layer_version.pymupdf]
}

resource "aws_lambda_function" "router" {
  filename         = data.archive_file.router_lambda_zip.output_path
  function_name    = "ally-router"
  role            = aws_iam_role.lambda_role.arn
  handler         = "router_lambda.lambda_handler"
  runtime         = "python3.13"
  architectures    = ["arm64"]
  timeout         = 900
  source_code_hash = data.archive_file.router_lambda_zip.output_base64sha256
}

resource "aws_lambda_function" "pdf_metadata" {
  filename         = data.archive_file.pdf_metadata_lambda_zip.output_path
  function_name    = "ally-pdf-metadata"
  role            = aws_iam_role.lambda_role.arn
  handler         = "pdf_metadata_lambda.lambda_handler"
  runtime         = "python3.13"
  architectures    = ["arm64"]
  timeout         = 900
  source_code_hash = data.archive_file.pdf_metadata_lambda_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.pymupdf.arn, aws_lambda_layer_version.adobe_pdf_services.arn]
  depends_on       = [aws_lambda_layer_version.pymupdf, aws_lambda_layer_version.adobe_pdf_services]
  
  environment {
    variables = {
      PDF_SERVICES_CLIENT_ID     = data.aws_ssm_parameter.pdf_services_client_id.value
      PDF_SERVICES_CLIENT_SECRET = data.aws_ssm_parameter.pdf_services_client_secret.value
    }
  }
}

resource "aws_lambda_permission" "bedrock_invoke" {
  statement_id  = "AllowBedrockInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.document_analyzer.function_name
  principal     = "bedrock.amazonaws.com"
  source_arn    = "arn:aws:bedrock:us-east-1:${data.aws_caller_identity.current.account_id}:agent/*"
}

resource "aws_lambda_permission" "bedrock_invoke_fixer" {
  statement_id  = "AllowBedrockInvokeFixer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.document_fixer.function_name
  principal     = "bedrock.amazonaws.com"
  source_arn    = "arn:aws:bedrock:us-east-1:${data.aws_caller_identity.current.account_id}:agent/*"
}

resource "aws_lambda_permission" "bedrock_invoke_router" {
  statement_id  = "AllowBedrockInvokeRouter"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.router.function_name
  principal     = "bedrock.amazonaws.com"
  source_arn    = "arn:aws:bedrock:us-east-1:${data.aws_caller_identity.current.account_id}:agent/*"
}

resource "aws_lambda_permission" "bedrock_invoke_pdf_metadata" {
  statement_id  = "AllowBedrockInvokePDFMetadata"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pdf_metadata.function_name
  principal     = "bedrock.amazonaws.com"
  source_arn    = "arn:aws:bedrock:us-east-1:${data.aws_caller_identity.current.account_id}:agent/*"
}

variable "action_group_state" {
  description = "State of the action group (ENABLED or DISABLED)"
  type        = string
  default     = "ENABLED"
}

variable "agent_name" {
  description = "Name of the Bedrock agent"
  type        = string
  default     = "ally-document-agent"
}

variable "agent_alias_name" {
  description = "Alias name for the Bedrock agent"
  type        = string
  default     = "Samantha"
}

# Create inference profile for Claude Sonnet 4
resource "aws_bedrock_inference_profile" "claude_sonnet_4" {
  name                  = "ally-claude-sonnet-4-profile"
  description           = "Inference profile for Claude Sonnet 4"
  model_source {
    copy_from = "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-20250514-v1:0"
  }
}

# Action Group for the agent
resource "aws_bedrockagent_agent_action_group" "document_analysis_group" {
  agent_id                    = aws_bedrockagent_agent.ally_agent.id
  agent_version              = "DRAFT"
  action_group_name          = "DocumentAnalysisGroup"
  description                = "Action group for document accessibility analysis"
  action_group_state         = var.action_group_state
  action_group_executor {
    lambda = aws_lambda_function.document_analyzer.arn
  }
  api_schema {
    payload = file("${path.module}/../action_group_schema.json")
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

# PDF Metadata Action Group
resource "aws_bedrockagent_agent_action_group" "pdf_metadata_group" {
  agent_id                    = aws_bedrockagent_agent.ally_agent.id
  agent_version              = "DRAFT"
  action_group_name          = "PDFMetadataGroup"
  description                = "Action group for PDF metadata fixing (title and language)"
  action_group_state         = var.action_group_state
  action_group_executor {
    lambda = aws_lambda_function.pdf_metadata.arn
  }
  api_schema {
    payload = file("${path.module}/../pdf_metadata_schema.json")
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

# Create an alias for the agent
resource "aws_bedrockagent_agent_alias" "ally_agent_alias" {
  agent_id    = aws_bedrockagent_agent.ally_agent.id
  agent_alias_name = var.agent_alias_name
  depends_on = [
    aws_bedrockagent_agent_action_group.document_analysis_group,
    aws_bedrockagent_agent_action_group.pdf_metadata_group
  ]
}

#!/bin/bash

# Deploy script for Ally Document Agent
# Usage: ./deploy.sh [AGENT_NAME] [ALIAS_NAME]
# Example: ./deploy.sh "my-accessibility-agent" "Alex"

set -e

# Default values
DEFAULT_AGENT_NAME="ally-document-agent"
DEFAULT_ALIAS_NAME="Samantha"

# Get parameters from command line or use defaults
AGENT_NAME="${1:-$DEFAULT_AGENT_NAME}"
ALIAS_NAME="${2:-$DEFAULT_ALIAS_NAME}"

echo "Deploying Ally Document Agent..."
echo "Agent Name: $AGENT_NAME"
echo "Alias Name: $ALIAS_NAME"
echo ""

# Run Terraform with variables
terraform init
terraform plan -var="agent_name=$AGENT_NAME" -var="agent_alias_name=$ALIAS_NAME"
terraform apply -var="agent_name=$AGENT_NAME" -var="agent_alias_name=$ALIAS_NAME" -auto-approve

echo ""
echo "Deployment complete!"
echo "Agent Name: $AGENT_NAME"
echo "Alias Name: $ALIAS_NAME"
#!/bin/bash

# Check if collection id is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <collection-id>"
    echo "Example: $0 my-collection"
    exit 1
fi

COLLECTION_ID="$1"

# First, get your OpenSearch collection endpoint
echo "Getting endpoint for collection: $COLLECTION_ID"
ENDPOINT=$(aws opensearchserverless batch-get-collection --profile performance --region us-east-1 --ids "$COLLECTION_ID" --query 'collectionDetails[0].collectionEndpoint' --output text)

if [ -z "$ENDPOINT" ]; then
    echo "Error: Could not get endpoint for collection $COLLECTION_ID"
    exit 1
fi

SESSION_TOKEN=$(aws configure export-credentials --profile=performance --output json | jq -r '.SessionToken')
ACCESS_KEY_ID=$(aws configure export-credentials --profile=performance --output json | jq -r '.AccessKeyId')
SECRET_ACCESS_KEY=$(aws configure export-credentials --profile=performance --output json | jq -r '.SecretAccessKey')
USER_KEY="$ACCESS_KEY_ID:$SECRET_ACCESS_KEY"

echo "Creating index on endpoint: $ENDPOINT"

curl -v --aws-sigv4 aws:amz:us-east-1:aoss --user $USER_KEY -X PUT "${ENDPOINT}/bedrock-knowledge-base-default-index" \
  -H "Content-Type: application/json" \
  -H "x-amz-security-token:$SESSION_TOKEN" \
  -H "x-amz-content-sha256: UNSIGNED_PAYLOAD" \
  -d '{
    "settings": {
      "index": {
        "knn": true,
        "knn.algo_param.ef_search": 512
      }
    },
    "mappings": {
      "properties": {
        "bedrock-knowledge-base-default-vector": {
          "type": "knn_vector",
          "dimension": 1024,
          "method": {
            "engine": "faiss",
            "name": "hnsw",
            "space_type": "l2"
          }
        },
        "AMAZON_BEDROCK_METADATA": {
          "type": "text",
          "index": false
        },
        "AMAZON_BEDROCK_TEXT_CHUNK": {
          "type": "text",
          "index": true
        }
      }
    }
  }'

# Check the exit status of the last command
if [ $? -eq 0 ]; then
    echo "Successfully created index for collection: $COLLECTION_ID"
else
    echo "Error creating index for collection: $COLLECTION_ID"
    exit 1
fi
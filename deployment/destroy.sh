#!/bin/bash

echo "Disabling action group before destroying resources..."
terraform apply -var="action_group_state=DISABLED" -auto-approve

echo "Destroying all resources..."
terraform destroy -auto-approve

echo "Cleanup complete!"
#!/usr/bin/env bash
# Re-exec under bash when azd invokes this script with sh
if [ -z "$BASH_VERSION" ]; then exec bash "$0" "$@"; fi
# Registers Azure resource providers and preview feature flags required for
# Application Gateway for Containers (AGFC) AKS add-on before azd provisions
# the infrastructure.
set -euo pipefail

# Skip entirely if AGFC is not enabled (saves ~6 minutes).
enableAgfc=$(azd env get-value ENABLE_AGFC 2>/dev/null || echo "false")
if [[ "$enableAgfc" != "true" ]]; then
    echo "==> AGFC disabled — skipping provider/feature registration (fast mode)."
    exit 0
fi

echo "==> Installing required Azure CLI extensions..."
az extension add --name aks-preview --upgrade --allow-preview true
az extension add --name alb --upgrade

echo "==> Registering required resource providers..."
az provider register --namespace Microsoft.ServiceNetworking
az provider register --namespace Microsoft.NetworkFunction
az provider register --namespace Microsoft.ContainerService

echo "==> Registering AKS preview feature flags for Gateway API + ALB add-on..."
az feature register --namespace 'Microsoft.ContainerService' --name 'ManagedGatewayAPIPreview'
az feature register --namespace 'Microsoft.ContainerService' --name 'ApplicationLoadBalancerPreview'

echo "==> Waiting for feature registration (this may take a few minutes)..."
for feature in ManagedGatewayAPIPreview ApplicationLoadBalancerPreview; do
    max_retries=36   # 36 x 10s = 6 minutes
    retries=0
    while true; do
        state=$(az feature show --namespace 'Microsoft.ContainerService' --name "$feature" --query 'properties.state' -o tsv)
        if [[ "$state" == "Registered" ]]; then
            echo "  $feature : Registered OK"
            break
        fi
        echo "  $feature : $state - waiting 10 s..."
        sleep 10
        retries=$((retries + 1))
        if [[ $retries -ge $max_retries ]]; then
            echo "WARNING: Feature '$feature' did not reach Registered state within timeout. Continuing anyway." >&2
            break
        fi
    done
done

# Re-register ContainerService so the new features take effect.
az provider register --namespace Microsoft.ContainerService

echo "==> Pre-provisioning complete."

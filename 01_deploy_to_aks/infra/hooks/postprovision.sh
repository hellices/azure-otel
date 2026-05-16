#!/usr/bin/env bash
# Re-exec under bash when azd invokes this script with sh
if [ -z "$BASH_VERSION" ]; then exec bash "$0" "$@"; fi
# Post-provision hook:
#   1. Enables the AKS Gateway API + Application Load Balancer add-on.
#   2. Merges kubeconfig and waits for the ALB controller to be ready.
#   3. Reads the pre-provisioned 'aks-appgateway' subnet ID from azd output.
#   4. Grants the ALB managed identity Network Contributor on that subnet.
set -euo pipefail

# ---------- Read azd environment outputs ----------
rg=$(azd env get-value AZURE_RESOURCE_GROUP)
aksName=$(azd env get-value AKS_NAME)
subnetId=$(azd env get-value AGFC_SUBNET_ID)

echo "==> Enabling Gateway API + ALB add-on on '$aksName' (rg: $rg) ..."
az aks update \
    --name "$aksName" \
    --resource-group "$rg" \
    --enable-gateway-api \
    --enable-application-load-balancer

echo "==> Fetching kubeconfig..."
az aks get-credentials --resource-group "$rg" --name "$aksName" --overwrite-existing

echo "==> Waiting for ALB controller pods (up to 3 min)..."
deadline=$((SECONDS + 180))
ready=""
while [[ -z "$ready" && $SECONDS -lt $deadline ]]; do
    ready=$(kubectl -n kube-system get pods -l app=alb-controller \
                --field-selector=status.phase=Running \
                -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
    if [[ -z "$ready" ]]; then
        echo "  ALB controller not yet ready -- waiting 10 s..."
        sleep 10
    fi
done

if [[ -z "$ready" ]]; then
    echo "WARNING: ALB controller pods not Running after 3 min." >&2
fi

echo "==> Waiting for managed GatewayClass registration..."
gcDeadline=$((SECONDS + 180))
gcAccepted=""
while [[ "$gcAccepted" != "True" && $SECONDS -lt $gcDeadline ]]; do
    gcAccepted=$(kubectl get gatewayclass azure-alb-external \
        -o 'jsonpath={.status.conditions[?(@.type=="Accepted")].status}' 2>/dev/null || true)
    if [[ "$gcAccepted" != "True" ]]; then
        echo "  GatewayClass not yet accepted -- waiting 10 s..."
        sleep 10
    fi
done

if [[ "$gcAccepted" != "True" ]]; then
    echo "WARNING: GatewayClass 'azure-alb-external' is not Accepted yet." >&2
fi

echo "==> Granting AGFC managed identity access to the delegated subnet..."
nodeResourceGroup=$(az aks show --resource-group "$rg" --name "$aksName" --query 'nodeResourceGroup' -o tsv)
albIdentityName="applicationloadbalancer-${aksName}"

identityDeadline=$((SECONDS + 180))
albPrincipalId=""
while [[ -z "$albPrincipalId" && $SECONDS -lt $identityDeadline ]]; do
    albPrincipalId=$(az identity show --resource-group "$nodeResourceGroup" --name "$albIdentityName" --query 'principalId' -o tsv 2>/dev/null || true)
    if [[ -z "$albPrincipalId" ]]; then
        echo "  Managed identity '$albIdentityName' not yet visible -- waiting 10 s..."
        sleep 10
    fi
done

if [[ -z "$albPrincipalId" ]]; then
    echo "ERROR: Could not resolve managed identity '$albIdentityName' in '$nodeResourceGroup'." >&2
    exit 1
fi

existingSubnetRole=$(az role assignment list \
    --assignee-object-id "$albPrincipalId" \
    --scope "$subnetId" \
    --role 'Network Contributor' \
    --query '[0].id' -o tsv 2>/dev/null || true)

if [[ -z "$existingSubnetRole" ]]; then
    az role assignment create \
        --assignee-object-id "$albPrincipalId" \
        --assignee-principal-type ServicePrincipal \
        --role 'Network Contributor' \
        --scope "$subnetId" \
        --only-show-errors > /dev/null
    echo "  Granted Network Contributor on AGFC subnet to '$albIdentityName'."
else
    echo "  Network Contributor already granted on AGFC subnet."
fi

# Verify role propagation
verifyDeadline=$((SECONDS + 120))
verified=""
while [[ -z "$verified" && $SECONDS -lt $verifyDeadline ]]; do
    verified=$(az role assignment list \
        --assignee-object-id "$albPrincipalId" \
        --scope "$subnetId" \
        --role 'Network Contributor' \
        --query '[0].id' -o tsv 2>/dev/null || true)
    if [[ -z "$verified" ]]; then
        echo "  Waiting 10 s for role assignment to propagate..."
        sleep 10
    fi
done

if [[ -z "$verified" ]]; then
    echo "ERROR: ALB MSI '$albIdentityName' still lacks 'Network Contributor' on '$subnetId' after 2 min." >&2
    exit 1
fi

echo "  Using AGFC subnet: $subnetId"

echo ""
echo "==> Infrastructure ready. Deploy the app with Helm:"
echo "    helm upgrade --install azure-otel ./azure-otel \\"
echo "        --namespace azure-otel --create-namespace \\"
echo "        --set \"gateway.subnetId=\$(azd env get-value AGFC_SUBNET_ID)\" \\"
echo "        --wait --timeout 10m"

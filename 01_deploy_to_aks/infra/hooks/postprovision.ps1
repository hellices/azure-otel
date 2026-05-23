<#
.SYNOPSIS
  Post-provision hook:
    1. (If AGFC enabled) Enables the AKS Gateway API + Application Load Balancer add-on.
    2. Merges kubeconfig and waits for the ALB controller to be ready.
    3. Reads the pre-provisioned 'aks-appgateway' subnet ID from azd output.
    4. Grants the ALB managed identity Network Contributor on that subnet.
#>
$ErrorActionPreference = 'Stop'
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')

# ---------- Read azd environment outputs ----------
$rg        = azd env get-value AZURE_RESOURCE_GROUP
$aksName   = azd env get-value AKS_NAME
$enableAgfc = azd env get-value ENABLE_AGFC 2>$null

# ---------- Skip AGFC if disabled ----------
if ($enableAgfc -ne 'true') {
    Write-Host "==> AGFC disabled (ENABLE_AGFC=$enableAgfc). Fetching kubeconfig only..."
    az aks get-credentials --resource-group $rg --name $aksName --overwrite-existing

    $enableAppGw = azd env get-value ENABLE_APPGW 2>$null
    if ($enableAppGw -eq 'true') {
        $appGwIp = azd env get-value APPGW_PUBLIC_IP 2>$null
        Write-Host ""
        Write-Host "==> Application Gateway mode. Public IP: $appGwIp"
        Write-Host "    Access the app at: http://$appGwIp"
        Write-Host ""
        Write-Host "==> Deploying app with Helm (appGw mode)..."
        helm upgrade --install azure-otel ./azure-otel `
            --namespace azure-otel --create-namespace `
            --set gateway.enabled=false `
            --set appGw.enabled=true `
            --wait --timeout 5m
    } else {
        Write-Host ""
        Write-Host "==> Deploying app with Helm (public LB mode)..."
        helm upgrade --install azure-otel ./azure-otel `
            --namespace azure-otel --create-namespace `
            --set gateway.enabled=false `
            --set appGw.enabled=false `
            --set loadBalancer.enabled=true `
            --wait --timeout 5m
    }
    exit 0
}

$subnetId  = azd env get-value AGFC_SUBNET_ID

# Microsoft.AlbController extension is not GA in every region (e.g. koreacentral
# returns ExtensionTypeRegistrationGetFailed when installed via ARM/Bicep).
# The AKS CLI add-on handles region availability internally, so install it here.
Write-Host "==> Enabling Gateway API + ALB add-on on '$aksName' (rg: $rg) ..."
az aks update `
    --name $aksName `
    --resource-group $rg `
    --enable-gateway-api `
    --enable-application-load-balancer

Write-Host "==> Fetching kubeconfig..."
az aks get-credentials --resource-group $rg --name $aksName --overwrite-existing

Write-Host "==> Waiting for ALB controller pods (up to 3 min)..."
$deadline = (Get-Date).AddMinutes(3)
do {
    $ready = kubectl -n kube-system get pods -l app=alb-controller `
                 --field-selector=status.phase=Running `
                 -o jsonpath='{.items[*].metadata.name}' 2>$null
    if (-not $ready) {
        Write-Host "  ALB controller not yet ready -- waiting 10 s..."
        Start-Sleep -Seconds 10
    }
} while (-not $ready -and (Get-Date) -lt $deadline)

if (-not $ready) {
    Write-Warning "ALB controller pods not Running after 3 min. Helm install may fail - check 'kubectl -n kube-system get pods -l app=alb-controller'."
}

Write-Host "==> Waiting for managed GatewayClass registration..."
$gatewayClassDeadline = (Get-Date).AddMinutes(3)
do {
    $gatewayClassAccepted = kubectl get gatewayclass azure-alb-external -o 'jsonpath={.status.conditions[?(@.type==\"Accepted\")].status}' 2>$null
    if ($gatewayClassAccepted -ne 'True') {
        Write-Host "  GatewayClass not yet accepted -- waiting 10 s..."
        Start-Sleep -Seconds 10
    }
} while ($gatewayClassAccepted -ne 'True' -and (Get-Date) -lt $gatewayClassDeadline)

if ($gatewayClassAccepted -ne 'True') {
    Write-Warning "GatewayClass 'azure-alb-external' is not Accepted yet. Continuing, but Gateway programming may be delayed."
}

Write-Host "==> Granting AGFC managed identity access to the delegated subnet..."
$nodeResourceGroup = az aks show --resource-group $rg --name $aksName --query 'nodeResourceGroup' -o tsv
$albIdentityName = "applicationloadbalancer-$aksName"
$identityDeadline = (Get-Date).AddMinutes(3)
$albPrincipalId = $null
do {
    $albPrincipalId = az identity show --resource-group $nodeResourceGroup --name $albIdentityName --query 'principalId' -o tsv 2>$null
    if (-not $albPrincipalId) {
        Write-Host "  Managed identity '$albIdentityName' not yet visible -- waiting 10 s..."
        Start-Sleep -Seconds 10
    }
} while (-not $albPrincipalId -and (Get-Date) -lt $identityDeadline)

if (-not $albPrincipalId) {
    throw "Could not resolve managed identity '$albIdentityName' in '$nodeResourceGroup'."
}

$existingSubnetRole = az role assignment list `
    --assignee-object-id $albPrincipalId `
    --scope $subnetId `
    --role 'Network Contributor' `
    --query '[0].id' -o tsv 2>$null

if (-not $existingSubnetRole) {
    az role assignment create `
        --assignee-object-id $albPrincipalId `
        --assignee-principal-type ServicePrincipal `
        --role 'Network Contributor' `
        --scope $subnetId `
        --only-show-errors | Out-Null
    Write-Host "  Granted Network Contributor on AGFC subnet to '$albIdentityName'."
} else {
    Write-Host "  Network Contributor already granted on AGFC subnet."
}

# Verify (RBAC propagation can lag a few seconds). Fail loudly if missing —
# without this role the ALB controller hits LinkedAuthorizationFailed and the
# Gateway never gets a public address.
$verifyDeadline = (Get-Date).AddMinutes(2)
do {
    $verified = az role assignment list `
        --assignee-object-id $albPrincipalId `
        --scope $subnetId `
        --role 'Network Contributor' `
        --query '[0].id' -o tsv 2>$null
    if (-not $verified) {
        Write-Host "  Waiting 10 s for role assignment to propagate..."
        Start-Sleep -Seconds 10
    }
} while (-not $verified -and (Get-Date) -lt $verifyDeadline)

if (-not $verified) {
    throw "ALB MSI '$albIdentityName' still lacks 'Network Contributor' on '$subnetId' after 2 min. Re-run 'azd provision' or assign the role manually."
}

Write-Host "  Using AGFC subnet: $subnetId"

# ---------- Done ----------
# Helm chart install is intentionally left out of this hook so it can be
# managed independently. To deploy the application:
#
#   $subnetId = azd env get-value AGFC_SUBNET_ID
#   helm upgrade --install azure-otel ./azure-otel `
#       --namespace azure-otel --create-namespace `
#       --set "gateway.subnetId=$subnetId" `
#       --wait --timeout 10m
#
#   kubectl -n azure-otel get gateway azure-otel-gw `
#       -o 'jsonpath={.status.addresses[0].value}'

Write-Host ""
Write-Host "==> Infrastructure ready. Deploy the app with Helm:"
Write-Host "    helm upgrade --install azure-otel ./azure-otel ``"
Write-Host "        --namespace azure-otel --create-namespace ``"
Write-Host "        --set `"gateway.subnetId=`$(azd env get-value AGFC_SUBNET_ID)`" ``"
Write-Host "        --wait --timeout 10m"


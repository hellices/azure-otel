<#
.SYNOPSIS
  Registers Azure resource providers and preview feature flags required for
  Application Gateway for Containers (AGFC) AKS add-on before azd provisions
  the infrastructure.
#>
$ErrorActionPreference = 'Stop'
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')

Write-Host "==> Installing required Azure CLI extensions..."
az extension add --name aks-preview --upgrade --allow-preview true
az extension add --name alb --upgrade

Write-Host "==> Registering required resource providers..."
az provider register --namespace Microsoft.ServiceNetworking
az provider register --namespace Microsoft.NetworkFunction
az provider register --namespace Microsoft.ContainerService

Write-Host "==> Registering AKS preview feature flags for Gateway API + ALB add-on..."
az feature register --namespace 'Microsoft.ContainerService' --name 'ManagedGatewayAPIPreview'
az feature register --namespace 'Microsoft.ContainerService' --name 'ApplicationLoadBalancerPreview'

Write-Host "==> Waiting for feature registration (this may take a few minutes)..."
$features = @('ManagedGatewayAPIPreview', 'ApplicationLoadBalancerPreview')
foreach ($feature in $features) {
    $maxRetries = 36   # 36 x 10s = 6 minutes
    $retries = 0
    do {
        $state = az feature show --namespace 'Microsoft.ContainerService' --name $feature --query 'properties.state' -o tsv
        if ($state -ne 'Registered') {
            Write-Host "  $feature : $state - waiting 10 s..."
            Start-Sleep -Seconds 10
            $retries++
        }
    } while ($state -ne 'Registered' -and $retries -lt $maxRetries)

    if ($retries -ge $maxRetries) {
        Write-Warning "Feature '$feature' did not reach Registered state within timeout. Continuing anyway - azd up may fail if the region does not support ALB add-on."
    } else {
        Write-Host "  $feature : Registered OK"
    }
}

# Re-register ContainerService so the new features take effect.
az provider register --namespace Microsoft.ContainerService

Write-Host "==> Pre-provisioning complete."

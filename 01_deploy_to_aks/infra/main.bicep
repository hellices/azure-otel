targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment; drives resource naming.')
param environmentName string

@minLength(1)
@description('Primary location for all resources.')
param location string

@description('Object ID (oid) of the user/SP running azd up. Used to grant Grafana Admin and AKS RBAC. Leave empty to skip role assignments.')
param principalId string = ''

@description('When true, AKS API server is exposed only inside the VNet (private cluster). Defaults to false so kubectl works from your laptop.')
param enablePrivateCluster bool = false

@description('When true, provisions Application Gateway for Containers (AGFC) via the ALB add-on. Disable for fast hands-on sessions (~20 min faster).')
param enableAgfc bool = false

@description('When true, deploys Application Gateway v2 as a fast L7 ingress (parallel with AKS, no addon needed). Ignored when enableAgfc=true.')
param enableAppGw bool = true

@description('When true, creates Azure Monitor Private Link Scope (AMPLS) with private DNS zones and PE. Disable for fast provisioning (~5 min faster).')
param enableAmpls bool = true

@description('Number of AKS user-mode nodes for the default system pool.')
@minValue(2)
@maxValue(10)
param nodeCount int = 2

@description('VM size for AKS nodes.')
param nodeVmSize string = 'Standard_D4s_v5'

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
}

var locationNormalized = toLower(replace(location, ' ', ''))
var locationShortMap = {
  koreacentral: 'krc'
  koreasouth: 'krs'
  eastus: 'eus'
  eastus2: 'eus2'
  westus: 'wus'
  westus2: 'wus2'
  westeurope: 'weu'
  northeurope: 'neu'
  southeastasia: 'sea'
  japaneast: 'jpe'
}
var locationShort = locationShortMap[locationNormalized] ?? substring(locationNormalized, 0, min(3, length(locationNormalized)))
var envShort = substring(toLower(replace(environmentName, '-', '')), 0, min(6, length(replace(environmentName, '-', ''))))

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-otel-${envShort}-${locationShort}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  scope: rg
  name: 'resources'
  params: {
    environmentName: environmentName
    location: location
    tags: tags
    resourceToken: resourceToken
    principalId: principalId
    enablePrivateCluster: enablePrivateCluster
    enableAgfc: enableAgfc
    enableAppGw: enableAppGw && !enableAgfc
    enableAmpls: enableAmpls
    nodeCount: nodeCount
    nodeVmSize: nodeVmSize
  }
}

output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = subscription().tenantId
output AZURE_RESOURCE_GROUP string = rg.name
output AKS_NAME string = resources.outputs.aksName
output AKS_RESOURCE_GROUP string = rg.name
output LOG_ANALYTICS_WORKSPACE_NAME string = resources.outputs.logAnalyticsName
output APPLICATION_INSIGHTS_NAME string = resources.outputs.appInsightsName
output APPLICATION_INSIGHTS_CONNECTION_STRING string = resources.outputs.appInsightsConnectionString
output AZURE_MONITOR_WORKSPACE_NAME string = resources.outputs.amwName
output GRAFANA_NAME string = resources.outputs.grafanaName
output GRAFANA_ENDPOINT string = resources.outputs.grafanaEndpoint
output ACR_NAME string = resources.outputs.acrName
output ACR_LOGIN_SERVER string = resources.outputs.acrLoginServer
output ENABLE_AGFC string = string(enableAgfc)
output ENABLE_APPGW string = string(enableAppGw && !enableAgfc)
output AGFC_SUBNET_ID string = resources.outputs.agfcSubnetId
output APPGW_PUBLIC_IP string = resources.outputs.appGwPublicIp
output NODEJS_INTERNAL_IP string = resources.outputs.nodejsInternalIp
output PYTHON_INTERNAL_IP string = resources.outputs.pythonInternalIp
output VNET_NAME string = resources.outputs.vnetName

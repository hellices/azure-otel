param environmentName string
param location string
param tags object
param resourceToken string
param principalId string
param enablePrivateCluster bool
param nodeCount int
param nodeVmSize string

// ---------- Naming ----------
var workload = 'otel'
var envNormalized = toLower(replace(environmentName, '-', ''))
var envShort = substring(envNormalized, 0, min(6, length(envNormalized)))
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
var uniqueSuffix = substring(resourceToken, 0, 5)

var logAnalyticsName = 'law-${workload}-${envShort}-${locationShort}-${uniqueSuffix}'
var appInsightsName  = 'appi-${workload}-${envShort}-${locationShort}-${uniqueSuffix}'
var amwName          = 'amw-${workload}-${envShort}-${locationShort}-${uniqueSuffix}'
// Managed Grafana name must be <= 23 chars.
var grafanaName      = substring('graf-${workload}-${envShort}-${locationShort}-${uniqueSuffix}', 0, min(23, length('graf-${workload}-${envShort}-${locationShort}-${uniqueSuffix}')))
// ACR must be lowercase alphanumeric only and globally unique.
var acrName          = 'acr${workload}${envShort}${locationShort}${uniqueSuffix}'
var vnetName         = 'vnet-${workload}-${envShort}-${locationShort}'
var aksName          = 'aks-${workload}-${envShort}-${locationShort}'
var aksDnsPrefix     = 'aks-${workload}-${envShort}-${locationShort}'
var aksSubnetNsgName  = 'nsg-${workload}-${envShort}-${locationShort}-aks'
var agfcSubnetNsgName = 'nsg-${workload}-${envShort}-${locationShort}-agfc'

resource aksSubnetNsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: aksSubnetNsgName
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-internet-http-80'
        properties: {
          description: 'Allow inbound HTTP from Internet to AKS subnet.'
          priority: 200
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// NSG for the AGFC delegated subnet — allows public HTTP/HTTPS ingress.
resource agfcSubnetNsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: agfcSubnetNsgName
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-internet-http-80'
        properties: {
          description: 'Allow inbound HTTP from Internet to AGFC subnet.'
          priority: 200
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'allow-internet-https-443'
        properties: {
          description: 'Allow inbound HTTPS from Internet to AGFC subnet.'
          priority: 210
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// ---------- Networking (private VNet for AKS) ----------
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [ '10.240.0.0/16' ] }
    subnets: [
      {
        name: 'aks-subnet'
        properties: {
          addressPrefix: '10.240.0.0/22'
          networkSecurityGroup: {
            id: aksSubnetNsg.id
          }
          // Private endpoint policies allow PE for downstream PaaS later.
          privateLinkServiceNetworkPolicies: 'Enabled'
        }
      }
      {
        // Dedicated subnet for Application Gateway for Containers (AGFC).
        // Must be delegated to Microsoft.ServiceNetworking/trafficControllers
        // and sized >= /24 per AGFC requirements.
        name: 'aks-appgateway'
        properties: {
          addressPrefix: '10.240.8.0/24'
          networkSecurityGroup: {
            id: agfcSubnetNsg.id
          }
          delegations: [
            {
              name: 'agfc-delegation'
              properties: {
                serviceName: 'Microsoft.ServiceNetworking/trafficControllers'
              }
            }
          ]
        }
      }
    ]
  }
}

resource aksSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: vnet
  name: 'aks-subnet'
}

// ---------- Log Analytics + Application Insights (workspace-based) ----------
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    features: { enableLogAccessUsingOnlyResourcePermissions: true }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ---------- Azure Monitor Workspace (managed Prometheus) ----------
resource amw 'Microsoft.Monitor/accounts@2023-04-03' = {
  name: amwName
  location: location
  tags: tags
  properties: {}
}

// Data Collection Endpoint required to scrape Prometheus into AMW.
resource dce 'Microsoft.Insights/dataCollectionEndpoints@2023-03-11' = {
  name: 'dce-${workload}-${envShort}-${locationShort}-${uniqueSuffix}'
  location: location
  tags: tags
  kind: 'Linux'
  properties: {
    networkAcls: { publicNetworkAccess: 'Enabled' }
  }
}

// Data Collection Rule that ships Prometheus metrics to the AMW.
resource dcr 'Microsoft.Insights/dataCollectionRules@2023-03-11' = {
  name: 'dcr-${workload}-${envShort}-${locationShort}-${uniqueSuffix}'
  location: location
  tags: tags
  kind: 'Linux'
  properties: {
    dataCollectionEndpointId: dce.id
    dataSources: {
      prometheusForwarder: [
        {
          name: 'PrometheusDataSource'
          streams: [ 'Microsoft-PrometheusMetrics' ]
          labelIncludeFilter: {}
        }
      ]
    }
    destinations: {
      monitoringAccounts: [
        {
          name: 'MonitoringAccount1'
          accountResourceId: amw.id
        }
      ]
    }
    dataFlows: [
      {
        streams: [ 'Microsoft-PrometheusMetrics' ]
        destinations: [ 'MonitoringAccount1' ]
      }
    ]
  }
}

// ---------- Managed Grafana ----------
resource grafana 'Microsoft.Dashboard/grafana@2023-09-01' = {
  name: grafanaName
  location: location
  tags: tags
  sku: { name: 'Standard' }
  identity: { type: 'SystemAssigned' }
  properties: {
    grafanaIntegrations: {
      azureMonitorWorkspaceIntegrations: [
        { azureMonitorWorkspaceResourceId: amw.id }
      ]
    }
    publicNetworkAccess: 'Enabled'
    apiKey: 'Disabled'
    deterministicOutboundIP: 'Disabled'
    zoneRedundancy: 'Disabled'
  }
}

// ---------- Azure Container Registry ----------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

// ---------- AKS ----------
resource aks 'Microsoft.ContainerService/managedClusters@2024-09-01' = {
  name: aksName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  sku: { name: 'Base', tier: 'Standard' }
  properties: {
    dnsPrefix: aksDnsPrefix
    enableRBAC: true
    disableLocalAccounts: false
    apiServerAccessProfile: {
      enablePrivateCluster: enablePrivateCluster
    }
    networkProfile: {
      networkPlugin: 'azure'
      networkPluginMode: 'overlay'
      networkPolicy: 'cilium'
      networkDataplane: 'cilium'
      loadBalancerSku: 'standard'
      serviceCidr: '10.0.0.0/16'
      dnsServiceIP: '10.0.0.10'
    }
    agentPoolProfiles: [
      {
        name: 'system'
        mode: 'System'
        osType: 'Linux'
        osSKU: 'AzureLinux'
        vmSize: nodeVmSize
        count: nodeCount
        minCount: nodeCount
        maxCount: 6
        vnetSubnetID: aksSubnet.id
        type: 'VirtualMachineScaleSets'
        enableAutoScaling: true
        maxPods: 50
      }
    ]
    addonProfiles: {
      omsagent: {
        enabled: true
        config: {
          logAnalyticsWorkspaceResourceID: law.id
          useAADAuth: 'true'
        }
      }
    }
    azureMonitorProfile: {
      metrics: {
        enabled: true
        kubeStateMetrics: {
          metricLabelsAllowlist: ''
          metricAnnotationsAllowList: ''
        }
      }
    }
    oidcIssuerProfile: { enabled: true }
    securityProfile: {
      workloadIdentity: { enabled: true }
    }
  }
}

// Associate the Prometheus DCR with the AKS cluster so managed Prometheus
// metrics flow into the Azure Monitor Workspace.
resource dcra 'Microsoft.Insights/dataCollectionRuleAssociations@2023-03-11' = {
  scope: aks
  name: 'send-to-amw'
  properties: {
    dataCollectionRuleId: dcr.id
    description: 'Send AKS managed Prometheus metrics to the Azure Monitor Workspace.'
  }
}

// NOTE: ALB controller (Microsoft.AlbController extension) is enabled by the
// postprovision hook via `az aks update --enable-application-load-balancer`.
// As of 2026-05 the extension is not yet GA in every region (e.g. koreacentral
// returns `ExtensionTypeRegistrationGetFailed`), so installing it directly
// from Bicep would fail. The AKS-level CLI flag handles region availability
// internally.

// ---------- Role assignments ----------
// Grafana service identity needs to read metrics from the AMW.
var monitoringDataReaderRoleId = 'b0d8363b-8ddd-447d-831f-62ca05bff136' // Monitoring Data Reader
resource grafanaToAmwReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: amw
  name: guid(amw.id, grafana.id, monitoringDataReaderRoleId)
  properties: {
    principalId: grafana.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringDataReaderRoleId)
  }
}

// Optional: grant the deployer Grafana Admin + AKS cluster admin so they can sign in / kubectl.
var grafanaAdminRoleId = '22926164-76b3-42b3-bc55-97df8dab3e41' // Grafana Admin
var aksClusterAdminRoleId = '0ab0b1a8-8aac-4efd-b8c2-3ee1fb270be8' // Azure Kubernetes Service RBAC Cluster Admin
var aksClusterUserRoleId  = '4abbcc35-e782-43d8-92c5-2d3f1bd2253f' // Azure Kubernetes Service Cluster User Role
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull

resource principalGrafanaAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: grafana
  name: guid(grafana.id, principalId, grafanaAdminRoleId)
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', grafanaAdminRoleId)
  }
}

resource principalAksClusterUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: aks
  name: guid(aks.id, principalId, aksClusterUserRoleId)
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aksClusterUserRoleId)
  }
}

resource principalAksClusterAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: aks
  name: guid(aks.id, principalId, aksClusterAdminRoleId)
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', aksClusterAdminRoleId)
  }
}

// Let AKS nodes pull images from ACR.
resource aksKubeletAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, aks.id, acrPullRoleId)
  properties: {
    principalId: aks.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

// ---------- Azure Monitor Private Link Scope (AMPLS) ----------
// Used by step 03 (OTel Collector → Application Insights) so that trace
// ingestion stays inside the VNet. Scope is left open (Open/Open) to keep
// cross-subscription monitoring traffic working — flip to PrivateOnly later
// if the environment is fully locked down.
resource ampls 'microsoft.insights/privateLinkScopes@2021-07-01-preview' = {
  name: 'ampls-${workload}-${envShort}-${locationShort}-${uniqueSuffix}'
  location: 'global'
  tags: tags
  properties: {
    accessModeSettings: {
      ingestionAccessMode: 'Open'
      queryAccessMode: 'Open'
    }
  }
}

resource amplsAppInsightsLink 'microsoft.insights/privateLinkScopes/scopedResources@2021-07-01-preview' = {
  parent: ampls
  name: 'appi-link'
  properties: {
    linkedResourceId: appInsights.id
  }
}

resource amplsLawLink 'microsoft.insights/privateLinkScopes/scopedResources@2021-07-01-preview' = {
  parent: ampls
  name: 'law-link'
  properties: {
    linkedResourceId: law.id
  }
}

// AMW Prometheus ingest goes through the DCE; the DCE itself is what gets
// scoped into AMPLS (AMW accounts cannot be linked directly). Without this,
// ama-metrics receives 403 InvalidAccess "Data collection endpoint must be
// used to access configuration over private link" from AMCS.
resource amplsDceLink 'microsoft.insights/privateLinkScopes/scopedResources@2021-07-01-preview' = {
  parent: ampls
  name: 'dce-link'
  properties: {
    linkedResourceId: dce.id
  }
}

// AMPLS DNS zones. Region-scoped zones (handler.control / ingest) are
// required for AMW Prometheus to resolve through the private endpoint.
// PE DNS zone groups are capped at 6 entries, so blob is dropped (AMPLS does
// not need it for our setup).
var amplsZones = [
  'privatelink.monitor.azure.com'
  'privatelink.oms.opinsights.azure.com'
  'privatelink.ods.opinsights.azure.com'
  'privatelink.agentsvc.azure-automation.net'
  'privatelink.${location}.handler.control.monitor.azure.com'
  'privatelink.${location}.ingest.monitor.azure.com'
]

resource amplsPrivateDnsZones 'Microsoft.Network/privateDnsZones@2024-06-01' = [for z in amplsZones: {
  name: z
  location: 'global'
  tags: tags
}]

resource amplsPrivateDnsLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [for (z, i) in amplsZones: {
  parent: amplsPrivateDnsZones[i]
  name: '${z}-link'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}]

// Private Endpoint into aks-subnet, with DNS zone group binding all 5 zones.
resource amplsPe 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-ampls-${workload}-${envShort}-${locationShort}'
  location: location
  tags: tags
  properties: {
    subnet: { id: aksSubnet.id }
    privateLinkServiceConnections: [
      {
        name: 'ampls'
        properties: {
          privateLinkServiceId: ampls.id
          groupIds: [ 'azuremonitor' ]
        }
      }
    ]
  }
  dependsOn: [
    amplsAppInsightsLink
    amplsLawLink
    amplsDceLink
  ]
}

resource amplsPeDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: amplsPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [for (z, i) in amplsZones: {
      name: replace(z, '.', '-')
      properties: {
        privateDnsZoneId: amplsPrivateDnsZones[i].id
      }
    }]
  }
}

// ---------- Outputs ----------
output aksName string = aks.name
output logAnalyticsName string = law.name
output appInsightsName string = appInsights.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output amwName string = amw.name
output grafanaName string = grafana.name
output grafanaEndpoint string = grafana.properties.endpoint
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output vnetName string = vnet.name
output agfcSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, 'aks-appgateway')

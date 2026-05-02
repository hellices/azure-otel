"""Build the 01_deploy_to_aks architecture .excalidraw using Azure SVG icons."""
import base64
import json
import os
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS_ROOT = ROOT / "libraries" / "azure-icons" / "Azure_Public_Service_Icons" / "Icons"
OUTPUT = Path(r"c:\Users\inhwanhwang\vscode\azure-otel\docs\diagrams\01-deploy-to-aks-architecture.excalidraw")

# Map of logical icon name -> filename within ICONS_ROOT (relative path)
ICONS = {
    "Subscription":       "general/10002-icon-service-Subscriptions.svg",
    "ResourceGroup":      "general/10007-icon-service-Resource-Groups.svg",
    "VNet":               "networking/10061-icon-service-Virtual-Networks.svg",
    "Subnet":             "networking/02742-icon-service-Subnet.svg",
    "NSG":                "networking/10067-icon-service-Network-Security-Groups.svg",
    "AKS":                "containers/10023-icon-service-Kubernetes-Services.svg",
    "ACR":                "containers/10105-icon-service-Container-Registries.svg",
    "AppGateway":         "networking/10076-icon-service-Application-Gateways.svg",
    "LogAnalytics":       "monitor/00009-icon-service-Log-Analytics-Workspaces.svg",
    "AppInsights":        "monitor/00012-icon-service-Application-Insights.svg",
    "Monitor":            "monitor/00001-icon-service-Monitor.svg",
    "Grafana":            "other/02905-icon-service-Azure-Managed-Grafana.svg",
}


def uid() -> str:
    return uuid.uuid4().hex[:16]


def now_ms() -> int:
    return int(time.time() * 1000)


def file_id_from_path(p: Path) -> str:
    # Excalidraw expects a stable id; hex of name is fine.
    return uuid.uuid5(uuid.NAMESPACE_URL, str(p)).hex[:40]


files_map: dict = {}
elements: list = []
order = [0]


def next_index() -> str:
    i = order[0]
    order[0] += 1
    return f"a{i:03d}"


def load_icon_file(key: str) -> str:
    p = ICONS_ROOT / ICONS[key]
    if not p.exists():
        raise FileNotFoundError(p)
    fid = file_id_from_path(p)
    if fid not in files_map:
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        files_map[fid] = {
            "mimeType": "image/svg+xml",
            "id": fid,
            "dataURL": f"data:image/svg+xml;base64,{b64}",
            "created": now_ms(),
            "lastRetrieved": now_ms(),
        }
    return fid


def add_image(key: str, x: float, y: float, size: float = 56) -> str:
    fid = load_icon_file(key)
    eid = uid()
    elements.append({
        "id": eid,
        "type": "image",
        "x": x,
        "y": y,
        "width": size,
        "height": size,
        "angle": 0,
        "strokeColor": "transparent",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "index": next_index(),
        "roundness": None,
        "seed": int.from_bytes(os.urandom(4), "big"),
        "version": 1,
        "versionNonce": int.from_bytes(os.urandom(4), "big"),
        "isDeleted": False,
        "boundElements": [],
        "updated": now_ms(),
        "link": None,
        "locked": False,
        "status": "saved",
        "fileId": fid,
        "scale": [1, 1],
    })
    return eid


def add_text(text: str, x: float, y: float, w: float, h: float = 22,
             font_size: int = 14, color: str = "#1e1e1e",
             align: str = "center") -> str:
    eid = uid()
    elements.append({
        "id": eid,
        "type": "text",
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "angle": 0,
        "strokeColor": color,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "index": next_index(),
        "roundness": None,
        "seed": int.from_bytes(os.urandom(4), "big"),
        "version": 1,
        "versionNonce": int.from_bytes(os.urandom(4), "big"),
        "isDeleted": False,
        "boundElements": [],
        "updated": now_ms(),
        "link": None,
        "locked": False,
        "text": text,
        "fontSize": font_size,
        "fontFamily": 5,
        "textAlign": align,
        "verticalAlign": "top",
        "containerId": None,
        "originalText": text,
        "lineHeight": 1.25,
        "autoResize": True,
    })
    return eid


def add_rect(x: float, y: float, w: float, h: float,
             stroke: str = "#1e1e1e", bg: str = "transparent",
             stroke_style: str = "solid", stroke_width: int = 2,
             label: str | None = None, label_color: str = "#1e1e1e",
             label_size: int = 14) -> str:
    eid = uid()
    elements.append({
        "id": eid,
        "type": "rectangle",
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": bg,
        "fillStyle": "hachure" if bg == "transparent" else "solid",
        "strokeWidth": stroke_width,
        "strokeStyle": stroke_style,
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "index": next_index(),
        "roundness": {"type": 3},
        "seed": int.from_bytes(os.urandom(4), "big"),
        "version": 1,
        "versionNonce": int.from_bytes(os.urandom(4), "big"),
        "isDeleted": False,
        "boundElements": [],
        "updated": now_ms(),
        "link": None,
        "locked": False,
    })
    if label:
        add_text(label, x + 12, y + 8, w - 24, h=20,
                 font_size=label_size, color=label_color, align="left")
    return eid


def add_arrow(x1: float, y1: float, x2: float, y2: float,
              color: str = "#1e1e1e", style: str = "solid",
              label: str | None = None, dashed: bool = False) -> str:
    eid = uid()
    elements.append({
        "id": eid,
        "type": "arrow",
        "x": x1,
        "y": y1,
        "width": abs(x2 - x1),
        "height": abs(y2 - y1),
        "angle": 0,
        "strokeColor": color,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "index": next_index(),
        "roundness": {"type": 2},
        "seed": int.from_bytes(os.urandom(4), "big"),
        "version": 1,
        "versionNonce": int.from_bytes(os.urandom(4), "big"),
        "isDeleted": False,
        "boundElements": [],
        "updated": now_ms(),
        "link": None,
        "locked": False,
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
        "startBinding": None,
        "endBinding": None,
        "startArrowhead": None,
        "endArrowhead": "arrow",
        "elbowed": False,
    })
    if label:
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        add_text(label, mx - 60, my - 18, 120, h=18,
                 font_size=11, color=color, align="center")
    return eid


# ---------------- Layout ----------------
ICON = 56

# Title
add_text("01 — Deploy to AKS (azd up) — Azure 리소스 구성도",
         60, 24, 1480, h=32, font_size=22, align="left")
add_text("Subscription-scope Bicep → ResourceGroup 모듈 → preprovision/postprovision hooks → Helm 차트 배포",
         60, 56, 1480, h=20, font_size=12, color="#5c5f66", align="left")

# Subscription frame
SUB_X, SUB_Y, SUB_W, SUB_H = 40, 100, 1520, 1080
add_rect(SUB_X, SUB_Y, SUB_W, SUB_H,
         stroke="#1971c2", bg="transparent", stroke_style="dashed")
add_image("Subscription", SUB_X + 14, SUB_Y + 12, 32)
add_text("Azure Subscription", SUB_X + 52, SUB_Y + 18, 240, h=22,
         font_size=16, color="#1971c2", align="left")

# Resource Group frame
RG_X, RG_Y, RG_W, RG_H = 70, 160, 1460, 1000
add_rect(RG_X, RG_Y, RG_W, RG_H,
         stroke="#0c8599", bg="#e3fafc", stroke_style="solid")
add_image("ResourceGroup", RG_X + 14, RG_Y + 10, 28)
add_text("Resource Group  rg-<env>  (location: koreacentral)",
         RG_X + 50, RG_Y + 16, 600, h=22,
         font_size=15, color="#0c8599", align="left")

# ============ Left: VNet block ============
VNET_X, VNET_Y, VNET_W, VNET_H = 100, 220, 720, 520
add_rect(VNET_X, VNET_Y, VNET_W, VNET_H,
         stroke="#7048e8", bg="#f3f0ff", stroke_style="solid")
add_image("VNet", VNET_X + 14, VNET_Y + 12, 28)
add_text("VNet  aotel-vnet-*   10.240.0.0/16",
         VNET_X + 50, VNET_Y + 18, 400, h=22,
         font_size=15, color="#5f3dc4", align="left")

# AKS subnet
AKS_SN_X, AKS_SN_Y, AKS_SN_W, AKS_SN_H = 130, 290, 660, 280
add_rect(AKS_SN_X, AKS_SN_Y, AKS_SN_W, AKS_SN_H,
         stroke="#1c7ed6", bg="#e7f5ff", stroke_style="solid")
add_image("Subnet", AKS_SN_X + 12, AKS_SN_Y + 10, 24)
add_text("aks-subnet  10.240.0.0/22",
         AKS_SN_X + 42, AKS_SN_Y + 14, 300, h=20,
         font_size=13, color="#1864ab", align="left")

# NSG attached to aks-subnet (top-right corner)
add_image("NSG", AKS_SN_X + AKS_SN_W - 60, AKS_SN_Y + 8, 32)
add_text("NSG  aks", AKS_SN_X + AKS_SN_W - 110, AKS_SN_Y + 44,
         100, h=16, font_size=10, color="#495057", align="center")

# AKS cluster icon (centered)
AKS_CX = AKS_SN_X + 80
AKS_CY = AKS_SN_Y + 80
add_image("AKS", AKS_CX, AKS_CY, 80)
add_text("AKS  aotel-aks-*", AKS_CX - 30, AKS_CY + 86, 140, h=20,
         font_size=14, color="#1864ab", align="center")
add_text("• Standard tier, AzureLinux\n"
         "• 3× Standard_D4s_v5  (autoscale 3–6)\n"
         "• Azure CNI Overlay + Cilium\n"
         "• NetworkPolicy: cilium\n"
         "• OIDC + Workload Identity\n"
         "• RBAC enabled",
         AKS_CX + 110, AKS_CY - 4, 360, h=120,
         font_size=12, color="#1e1e1e", align="left")

# AKS addons box
add_text("Addons:  omsagent (Container Insights)  ·  azureMonitorProfile.metrics (Managed Prometheus)",
         AKS_SN_X + 16, AKS_SN_Y + AKS_SN_H - 32, AKS_SN_W - 32, h=18,
         font_size=11, color="#495057", align="left")

# AGFC subnet
AGFC_SN_X, AGFC_SN_Y, AGFC_SN_W, AGFC_SN_H = 130, 590, 660, 130
add_rect(AGFC_SN_X, AGFC_SN_Y, AGFC_SN_W, AGFC_SN_H,
         stroke="#f08c00", bg="#fff4e6", stroke_style="solid")
add_image("Subnet", AGFC_SN_X + 12, AGFC_SN_Y + 10, 24)
add_text("aks-appgateway  10.240.8.0/24   (delegated → Microsoft.ServiceNetworking/trafficControllers)",
         AGFC_SN_X + 42, AGFC_SN_Y + 14, 600, h=20,
         font_size=12, color="#d9480f", align="left")

# NSG agfc
add_image("NSG", AGFC_SN_X + AGFC_SN_W - 60, AGFC_SN_Y + 8, 28)
add_text("NSG  agfc", AGFC_SN_X + AGFC_SN_W - 110, AGFC_SN_Y + 40,
         100, h=16, font_size=10, color="#495057", align="center")

# AGFC icon (postprovision)
add_image("AppGateway", AGFC_SN_X + 60, AGFC_SN_Y + 50, 56)
add_text("Application Gateway\nfor Containers (AGFC)",
         AGFC_SN_X + 130, AGFC_SN_Y + 50, 240, h=40,
         font_size=12, color="#d9480f", align="left")
add_text("postprovision hook 에서 활성화 · Helm 차트가 ALB/Gateway/HTTPRoute 생성",
         AGFC_SN_X + 130, AGFC_SN_Y + 90, 520, h=18,
         font_size=11, color="#5c5f66", align="left")

# ============ ACR (below VNet, left column) ============
ACR_X, ACR_Y = 100, 770
add_rect(ACR_X, ACR_Y, 340, 110,
         stroke="#0ca678", bg="#e6fcf5")
add_image("ACR", ACR_X + 16, ACR_Y + 26, 60)
add_text("Azure Container Registry", ACR_X + 90, ACR_Y + 18,
         240, h=20, font_size=14, color="#087f5b", align="left")
add_text("aotelacr*  ·  Standard SKU\nadminUserEnabled: false",
         ACR_X + 90, ACR_Y + 42, 240, h=40,
         font_size=11, color="#1e1e1e", align="left")

# ============ Right: Monitoring stack ============
MON_X, MON_Y, MON_W, MON_H = 860, 220, 660, 660
add_rect(MON_X, MON_Y, MON_W, MON_H,
         stroke="#e8590c", bg="#fff9db", stroke_style="dotted")
add_image("Monitor", MON_X + 14, MON_Y + 12, 28)
add_text("Monitoring  &  Observability",
         MON_X + 50, MON_Y + 18, 360, h=22,
         font_size=15, color="#d9480f", align="left")

# Log Analytics Workspace
LAW_X, LAW_Y = MON_X + 30, MON_Y + 70
add_rect(LAW_X, LAW_Y, 280, 120, stroke="#1c7ed6", bg="#ffffff")
add_image("LogAnalytics", LAW_X + 16, LAW_Y + 28, 64)
add_text("Log Analytics Workspace", LAW_X + 96, LAW_Y + 18,
         180, h=20, font_size=13, color="#1864ab", align="left")
add_text("law-otel-*\nretention 30d\nresource permissions",
         LAW_X + 96, LAW_Y + 42, 180, h=60,
         font_size=11, color="#1e1e1e", align="left")

# Application Insights
AI_X, AI_Y = MON_X + 350, MON_Y + 70
add_rect(AI_X, AI_Y, 280, 120, stroke="#1c7ed6", bg="#ffffff")
add_image("AppInsights", AI_X + 16, AI_Y + 28, 64)
add_text("Application Insights", AI_X + 96, AI_Y + 18,
         180, h=20, font_size=13, color="#1864ab", align="left")
add_text("appi-otel-*\nworkspace-based\n→ Log Analytics",
         AI_X + 96, AI_Y + 42, 180, h=60,
         font_size=11, color="#1e1e1e", align="left")

# AMW (Azure Monitor Workspace) + DCR/DCE
AMW_X, AMW_Y = MON_X + 30, MON_Y + 220
add_rect(AMW_X, AMW_Y, 280, 160, stroke="#7048e8", bg="#ffffff")
add_image("Monitor", AMW_X + 16, AMW_Y + 28, 64)
add_text("Azure Monitor Workspace", AMW_X + 96, AMW_Y + 18,
         180, h=20, font_size=13, color="#5f3dc4", align="left")
add_text("amw-otel-*\n(managed Prometheus)\n\n+ DCE / DCR\n  · Microsoft-PrometheusMetrics",
         AMW_X + 96, AMW_Y + 42, 180, h=110,
         font_size=11, color="#1e1e1e", align="left")

# Managed Grafana
GRAF_X, GRAF_Y = MON_X + 350, MON_Y + 220
add_rect(GRAF_X, GRAF_Y, 280, 160, stroke="#e8590c", bg="#ffffff")
add_image("Grafana", GRAF_X + 16, GRAF_Y + 36, 64)
add_text("Azure Managed Grafana", GRAF_X + 96, GRAF_Y + 18,
         180, h=20, font_size=13, color="#d9480f", align="left")
add_text("graf-otel-*  · Standard\nSystemAssigned identity\nAMW data source 연결",
         GRAF_X + 96, GRAF_Y + 42, 180, h=80,
         font_size=11, color="#1e1e1e", align="left")

# Role assignments box
ROLE_X, ROLE_Y = MON_X + 30, MON_Y + 410
add_rect(ROLE_X, ROLE_Y, 600, 230,
         stroke="#868e96", bg="#f8f9fa", stroke_style="dashed")
add_text("Role assignments (principalId 자동 주입)",
         ROLE_X + 16, ROLE_Y + 12, 460, h=20,
         font_size=13, color="#495057", align="left")
add_text(
    "• Deployer  →  Grafana Admin   (scope: Managed Grafana)\n"
    "• Deployer  →  AKS RBAC Cluster Admin + Cluster User   (scope: AKS)\n"
    "• Grafana MSI  →  Monitoring Data Reader   (scope: AMW)\n"
    "• AKS kubelet identity  →  AcrPull   (scope: ACR)",
    ROLE_X + 16, ROLE_Y + 40, 580, h=180,
    font_size=12, color="#1e1e1e", align="left")

# ============ Outside: azd up flow ============
FLOW_X, FLOW_Y = 100, 900
add_rect(FLOW_X, FLOW_Y, 720, 250,
         stroke="#212529", bg="#ffffff", stroke_style="solid")
add_text("`azd up`  실행 단계",
         FLOW_X + 16, FLOW_Y + 12, 400, h=22,
         font_size=14, color="#212529", align="left")
add_text(
    "1.  Subscription-scope Bicep  →  Resource Group 생성\n"
    "2.  RG 모듈로 VNet · AKS · 모니터링 · Grafana · role assignments 생성\n"
    "3.  preprovision hook  ·  Azure CLI 확장 설치, AGFC preview feature/provider 등록\n"
    "4.  postprovision hook  ·  AKS Gateway API + AGFC 활성화, ALB MSI 권한 부여,\n"
    "                              Helm 차트 azure-otel 설치  →  ALB / Gateway / HTTPRoute",
    FLOW_X + 16, FLOW_Y + 44, 700, h=200,
    font_size=12, color="#1e1e1e", align="left")

# ============ Arrows (data/dependency flows) ============
# AKS omsagent -> Log Analytics
add_arrow(AKS_CX + 90, AKS_CY + 30, LAW_X + 30, LAW_Y + 60,
          color="#1c7ed6", label="omsagent (Container Insights)")
# AKS managed Prometheus -> AMW
add_arrow(AKS_CX + 90, AKS_CY + 60, AMW_X + 30, AMW_Y + 60,
          color="#7048e8", label="azureMonitorProfile.metrics → DCR → AMW")
# App Insights -> LAW
add_arrow(AI_X + 30, AI_Y + 110, LAW_X + 250, LAW_Y + 110,
          color="#1c7ed6", label="workspace-based")
# Grafana -> AMW
add_arrow(GRAF_X + 20, GRAF_Y + 80, AMW_X + 270, AMW_Y + 80,
          color="#e8590c", label="data source")
# AKS kubelet -> ACR (AcrPull)
add_arrow(AKS_CX + 40, AKS_CY + 80, ACR_X + 200, ACR_Y + 20,
          color="#0ca678", label="AcrPull")
# Internet -> AGFC
add_arrow(60, AGFC_SN_Y + 80, AGFC_SN_X + 60, AGFC_SN_Y + 80,
          color="#d9480f", label="Internet  HTTP/HTTPS")
# AGFC -> AKS (HTTPRoute)
add_arrow(AGFC_SN_X + 200, AGFC_SN_Y + 50,
          AKS_CX + 40, AKS_SN_Y + AKS_SN_H - 40,
          color="#d9480f", label="HTTPRoute → Service",
          dashed=True)


# ---------------- Write file ----------------
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {
        "viewBackgroundColor": "#ffffff",
        "gridSize": 20,
    },
    "files": files_map,
}
OUTPUT.write_text(json.dumps(doc, indent=2), encoding="utf-8")
print(f"wrote: {OUTPUT}")
print(f"elements: {len(elements)}  embedded files: {len(files_map)}")

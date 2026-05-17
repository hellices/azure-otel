"""Build the 03_1 AKS auto-instrumentation architecture .excalidraw using Azure SVG icons."""
from __future__ import annotations
import base64
import json
import os
import uuid
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS_ROOT = ROOT / "libraries" / "Azure_Public_Service_Icons" / "Icons"
OUTPUT = ROOT.parents[2] / "docs" / "diagrams" / "03_1-aks-auto-instrumentation-flow.excalidraw"

ICONS = {
    "AKS":           "containers/10023-icon-service-Kubernetes-Services.svg",
    "AppInsights":   "monitor/00012-icon-service-Application-Insights.svg",
    "Monitor":       "monitor/00001-icon-service-Monitor.svg",
}

def uid() -> str:
    return uuid.uuid4().hex[:16]

def now_ms() -> int:
    return int(time.time() * 1000)

def file_id_from_path(p: Path) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, str(p)).hex[:40]

files_map: dict = {}
elements: list = []
order = [0]

def next_index() -> str:
    i = order[0]; order[0] += 1
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
        "id": eid, "type": "image",
        "x": x, "y": y, "width": size, "height": size,
        "angle": 0, "strokeColor": "transparent", "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "index": next_index(), "roundness": None,
        "seed": int.from_bytes(os.urandom(4), "big"),
        "version": 1, "versionNonce": int.from_bytes(os.urandom(4), "big"),
        "isDeleted": False, "boundElements": [], "updated": now_ms(),
        "link": None, "locked": False, "status": "saved", "fileId": fid, "scale": [1, 1],
    })
    return eid

def add_text(text: str, x: float, y: float, w: float, h: float = 22,
             font_size: int = 14, color: str = "#1e1e1e", align: str = "left") -> str:
    eid = uid()
    elements.append({
        "id": eid, "type": "text",
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "index": next_index(), "roundness": None,
        "seed": int.from_bytes(os.urandom(4), "big"),
        "version": 1, "versionNonce": int.from_bytes(os.urandom(4), "big"),
        "isDeleted": False, "boundElements": [], "updated": now_ms(),
        "link": None, "locked": False,
        "text": text, "fontSize": font_size, "fontFamily": 5,
        "textAlign": align, "verticalAlign": "top",
        "containerId": None, "originalText": text, "lineHeight": 1.25, "autoResize": True,
    })
    return eid

def add_rect(x: float, y: float, w: float, h: float,
             stroke: str = "#1e1e1e", bg: str = "transparent",
             stroke_style: str = "solid", stroke_width: int = 2) -> str:
    eid = uid()
    elements.append({
        "id": eid, "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid" if bg != "transparent" else "hachure",
        "strokeWidth": stroke_width, "strokeStyle": stroke_style,
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "index": next_index(), "roundness": {"type": 3},
        "seed": int.from_bytes(os.urandom(4), "big"),
        "version": 1, "versionNonce": int.from_bytes(os.urandom(4), "big"),
        "isDeleted": False, "boundElements": [], "updated": now_ms(),
        "link": None, "locked": False,
    })
    return eid

def add_arrow(x1: float, y1: float, x2: float, y2: float,
              color: str = "#1e1e1e", dashed: bool = False,
              label: str | None = None, stroke_width: int = 2) -> str:
    eid = uid()
    elements.append({
        "id": eid, "type": "arrow",
        "x": x1, "y": y1,
        "width": abs(x2 - x1), "height": abs(y2 - y1),
        "angle": 0, "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": stroke_width,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "index": next_index(), "roundness": {"type": 2},
        "seed": int.from_bytes(os.urandom(4), "big"),
        "version": 1, "versionNonce": int.from_bytes(os.urandom(4), "big"),
        "isDeleted": False, "boundElements": [], "updated": now_ms(),
        "link": None, "locked": False,
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": "arrow", "elbowed": False,
    })
    if label:
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        add_text(label, mx - 80, my - 18, 160, h=18,
                 font_size=12, color=color, align="center")
    return eid

def add_ellipse(x: float, y: float, w: float, h: float,
                stroke: str = "#1e1e1e", bg: str = "transparent",
                stroke_width: int = 2) -> str:
    eid = uid()
    elements.append({
        "id": eid, "type": "ellipse",
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid" if bg != "transparent" else "hachure",
        "strokeWidth": stroke_width, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "index": next_index(), "roundness": {"type": 2},
        "seed": int.from_bytes(os.urandom(4), "big"),
        "version": 1, "versionNonce": int.from_bytes(os.urandom(4), "big"),
        "isDeleted": False, "boundElements": [], "updated": now_ms(),
        "link": None, "locked": False,
    })
    return eid

# ===================== LAYOUT =====================

# ---------- Title ----------
add_text("03-1  ·  AKS Auto-Instrumentation  →  Application Insights  (no collector)",
         100, 20, 1200, h=36, font_size=24, color="#1971c2", align="left")
add_text("AKS-managed webhook injects Azure Monitor OpenTelemetry Distro  →  AMA forwards to App Insights  ·  zero extra pods",
         100, 56, 1200, h=18, font_size=12, color="#5c5f66", align="left")

# ---------- AKS cluster frame ----------
AKS_X, AKS_Y, AKS_W, AKS_H = 60, 90, 820, 660
add_rect(AKS_X, AKS_Y, AKS_W, AKS_H, stroke="#5b2bb3", bg="#f3e8ff", stroke_style="dashed")
add_image("AKS", AKS_X + 12, AKS_Y + 8, 44)
add_text("AKS cluster", AKS_X + 62, AKS_Y + 14, 200, h=26, font_size=18, color="#5b2bb3")
add_text("azure-monitor-app-monitoring enabled", AKS_X + 62, AKS_Y + 40, 400, h=16, font_size=11, color="#5c5f66")

# ---------- AKS Auto-Instrumentation Webhook ----------
WH_X, WH_Y, WH_W, WH_H = 540, 120, 310, 100
add_rect(WH_X, WH_Y, WH_W, WH_H, stroke="#7048e8", bg="#f3f0ff")
add_text("AKS Auto-Instrumentation Webhook", WH_X + 16, WH_Y + 14, 280, h=22, font_size=15, color="#5b2bb3")
add_text("Managed mutating admission webhook\nInjects Azure Monitor Distro init containers\nReads Instrumentation CR (monitor.azure.com/v1)",
         WH_X + 16, WH_Y + 38, 280, h=60, font_size=11, color="#5c5f66")

# ---------- Namespace: azure-otel ----------
NS_X, NS_Y, NS_W, NS_H = 90, 240, 440, 490
add_rect(NS_X, NS_Y, NS_W, NS_H, stroke="#0ca678", bg="#e6fcf5")
add_text("namespace: azure-otel", NS_X + 16, NS_Y + 10, 280, h=22, font_size=16, color="#0ca678")

# Instrumentation CR
CR_X, CR_Y, CR_W, CR_H = NS_X + 16, NS_Y + 45, NS_W - 32, 55
add_rect(CR_X, CR_Y, CR_W, CR_H, stroke="#7048e8", bg="#f3f0ff", stroke_style="dotted")
add_text("Instrumentation CR  ·  monitor.azure.com/v1", CR_X + 12, CR_Y + 8, CR_W - 24, h=18, font_size=13, color="#5b2bb3")
add_text("autoInstrumentationPlatforms: [Java, NodeJs]  ·  destination: App Insights connStr",
         CR_X + 12, CR_Y + 28, CR_W - 24, h=16, font_size=10, color="#5c5f66")

# ---------- Pod: Node.js ----------
P1_X, P1_Y, P1_W, P1_H = NS_X + 16, NS_Y + 120, NS_W - 32, 100
add_rect(P1_X, P1_Y, P1_W, P1_H, stroke="#2f9e44", bg="#d3f9d8")
add_ellipse(P1_X + 12, P1_Y + 12, 28, 28, stroke="#2f9e44", bg="#b2f2bb")
add_text("JS", P1_X + 17, P1_Y + 16, 18, h=18, font_size=13, color="#2b8a3e", align="center")
add_text("azure-otel-nodejs", P1_X + 50, P1_Y + 14, 200, h=22, font_size=16, color="#2b8a3e")
add_text("init: azure-monitor-distro  (injected by webhook)", P1_X + 50, P1_Y + 38, 340, h=16, font_size=11, color="#5c5f66")
add_rect(P1_X + 12, P1_Y + 60, P1_W - 24, 28, stroke="#2f9e44", bg="#ebfbee", stroke_width=1)
add_text("inject-nodejs: \"azure-otel\"", P1_X + 24, P1_Y + 65, 200, h=18, font_size=12, color="#2b8a3e")

# ---------- Pod: Python ----------
P2_X, P2_Y = NS_X + 16, NS_Y + 240
add_rect(P2_X, P2_Y, P1_W, P1_H, stroke="#1971c2", bg="#e7f5ff")
add_ellipse(P2_X + 12, P2_Y + 12, 28, 28, stroke="#1971c2", bg="#a5d8ff")
add_text("PY", P2_X + 17, P2_Y + 16, 18, h=18, font_size=13, color="#1864ab", align="center")
add_text("azure-otel-python", P2_X + 50, P2_Y + 14, 200, h=22, font_size=16, color="#1864ab")
add_text("private-preview-inject-python  (limited preview — opt-in)", P2_X + 50, P2_Y + 38, 340, h=16, font_size=11, color="#5c5f66")
add_rect(P2_X + 12, P2_Y + 60, P1_W - 24, 28, stroke="#1971c2", bg="#d0ebff", stroke_width=1)
add_text("annotation: private-preview-inject-python", P2_X + 24, P2_Y + 65, 320, h=18, font_size=12, color="#1864ab")

# ---------- Pod: Spring ----------
P3_X, P3_Y = NS_X + 16, NS_Y + 360
add_rect(P3_X, P3_Y, P1_W, P1_H, stroke="#e8590c", bg="#fff4e6")
add_ellipse(P3_X + 12, P3_Y + 12, 28, 28, stroke="#e8590c", bg="#ffd8a8")
add_text("J", P3_X + 20, P3_Y + 16, 14, h=18, font_size=13, color="#d9480f", align="center")
add_text("azure-otel-spring", P3_X + 50, P3_Y + 14, 200, h=22, font_size=16, color="#d9480f")
add_text("init: azure-monitor-distro  (injected by webhook)", P3_X + 50, P3_Y + 38, 340, h=16, font_size=11, color="#5c5f66")
add_rect(P3_X + 12, P3_Y + 60, P1_W - 24, 28, stroke="#e8590c", bg="#ffe8cc", stroke_width=1)
add_text("inject-java: \"azure-otel\"", P3_X + 24, P3_Y + 65, 200, h=18, font_size=12, color="#d9480f")

# ---------- AMA DaemonSet ----------
AMA_X, AMA_Y, AMA_W, AMA_H = 570, 350, 280, 140
add_rect(AMA_X, AMA_Y, AMA_W, AMA_H, stroke="#0c8599", bg="#e3fafc")
add_image("Monitor", AMA_X + 16, AMA_Y + 14, 48)
add_text("AMA DaemonSet", AMA_X + 72, AMA_Y + 14, 200, h=22, font_size=16, color="#0b7285")
add_text("Azure Monitor Agent\nOTLP/HTTP receiver  :4318\nAlready on cluster\n(no extra deployment)", AMA_X + 72, AMA_Y + 38, 200, h=80, font_size=11, color="#5c5f66")

# ---------- Application Insights (outside AKS) ----------
AI_X, AI_Y, AI_W, AI_H = 960, 160, 340, 320
add_rect(AI_X, AI_Y, AI_W, AI_H, stroke="#c2255c", bg="#fff0f6")
add_image("AppInsights", AI_X + 16, AI_Y + 14, 56)
add_text("Application Insights", AI_X + 80, AI_Y + 22, 240, h=26, font_size=18, color="#a61e4d")
add_text("(Azure Monitor)", AI_X + 80, AI_Y + 48, 240, h=18, font_size=12, color="#5c5f66")

# Feature items inside App Insights
features = [
    ("Live Metrics",       "#e64980"),
    ("Application Map",    "#c2255c"),
    ("Transaction Search", "#9c36b5"),
    ("Failures & Exceptions", "#d6336c"),
    ("Distributed Tracing", "#862e9c"),
]
for i, (feat, col) in enumerate(features):
    fy = AI_Y + 90 + i * 42
    add_rect(AI_X + 20, fy, AI_W - 40, 34, stroke=col, bg="#ffffff", stroke_width=1)
    add_text(feat, AI_X + 36, fy + 8, AI_W - 72, h=18, font_size=13, color=col)

# ---------- Comparison note ----------
NOTE_X, NOTE_Y = 960, 520
add_rect(NOTE_X, NOTE_Y, 340, 130, stroke="#868e96", bg="#f8f9fa", stroke_width=1)
add_text("vs step 03 (OTel Collector)", NOTE_X + 16, NOTE_Y + 10, 300, h=20, font_size=14, color="#495057")
add_text("✕  No OTel Collector  (zero extra pods)\n"
         "✕  No OTel Operator  (no cert-manager)\n"
         "✕  No manual collector config\n"
         "✓  AKS-managed webhook + AMA\n"
         "✓  CR: monitor.azure.com/v1",
         NOTE_X + 16, NOTE_Y + 34, 310, h=90, font_size=12, color="#1e1e1e")

# ===================== ARROWS =====================

# CR → Webhook (reads CR)
add_arrow(CR_X + CR_W, CR_Y + CR_H / 2,
          WH_X + WH_W / 2, WH_Y + WH_H,
          color="#7048e8", dashed=True, label="reads CR")

# Webhook → namespace (inject distro into pods)
add_arrow(WH_X, WH_Y + WH_H / 2,
          NS_X + NS_W, NS_Y + 180,
          color="#7048e8", dashed=True, label="inject distro")

# Node.js → AMA
add_arrow(P1_X + P1_W, P1_Y + P1_H / 2,
          AMA_X, AMA_Y + 30,
          color="#2f9e44", label="OTLP/HTTP")

# Python → AMA
add_arrow(P2_X + P1_W, P2_Y + P1_H / 2,
          AMA_X, AMA_Y + AMA_H / 2,
          color="#1971c2", label="OTLP/HTTP")

# Spring → AMA
add_arrow(P3_X + P1_W, P3_Y + P1_H / 2,
          AMA_X, AMA_Y + AMA_H - 30,
          color="#e8590c", label="OTLP/HTTP")

# AMA → App Insights
add_arrow(AMA_X + AMA_W, AMA_Y + AMA_H / 2,
          AI_X, AI_Y + AI_H / 2,
          color="#c2255c", label="forward telemetry")

# ---------- Flow numbering ----------
add_ellipse(490, 275, 28, 28, stroke="#7048e8", bg="#e5dbff")
add_text("1", 498, 279, 12, h=18, font_size=14, color="#5b2bb3", align="center")

add_ellipse(460, 400, 28, 28, stroke="#0c8599", bg="#c5f6fa")
add_text("2", 468, 404, 12, h=18, font_size=14, color="#0b7285", align="center")

add_ellipse(850, 380, 28, 28, stroke="#c2255c", bg="#fcc2d7")
add_text("3", 858, 384, 12, h=18, font_size=14, color="#a61e4d", align="center")

# ===================== WRITE =====================
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
print(f"Wrote: {OUTPUT}")
print(f"Elements: {len(elements)}  |  Embedded icon files: {len(files_map)}")

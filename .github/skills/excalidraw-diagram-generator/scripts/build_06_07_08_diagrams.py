"""Build excalidraw diagrams for steps 06 (Hubble), 07 (OpenCost), 08 (SLO)."""
from __future__ import annotations
import base64
import json
import os
import uuid
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS_ROOT = ROOT / "libraries" / "Azure_Public_Service_Icons" / "Icons"
DIAGRAMS = ROOT.parents[2] / "docs" / "diagrams"

ICONS = {
    "AKS":         "containers/10023-icon-service-Kubernetes-Services.svg",
    "AppInsights": "monitor/00012-icon-service-Application-Insights.svg",
    "Monitor":     "monitor/00001-icon-service-Monitor.svg",
    "Metrics":     "monitor/00020-icon-service-Metrics.svg",
}


def uid() -> str:
    return uuid.uuid4().hex[:16]

def now_ms() -> int:
    return int(time.time() * 1000)

def file_id_from_path(p: Path) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, str(p)).hex[:40]


class DiagramBuilder:
    def __init__(self):
        self.files_map: dict = {}
        self.elements: list = []
        self.order = 0

    def _next(self) -> str:
        i = self.order; self.order += 1
        return f"a{i:03d}"

    def _seed(self) -> int:
        return int.from_bytes(os.urandom(4), "big")

    def load_icon(self, key: str) -> str:
        p = ICONS_ROOT / ICONS[key]
        if not p.exists():
            raise FileNotFoundError(p)
        fid = file_id_from_path(p)
        if fid not in self.files_map:
            data = p.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            self.files_map[fid] = {
                "mimeType": "image/svg+xml", "id": fid,
                "dataURL": f"data:image/svg+xml;base64,{b64}",
                "created": now_ms(), "lastRetrieved": now_ms(),
            }
        return fid

    def image(self, key: str, x: float, y: float, size: float = 48):
        fid = self.load_icon(key)
        self.elements.append({
            "id": uid(), "type": "image", "x": x, "y": y,
            "width": size, "height": size, "angle": 0,
            "strokeColor": "transparent", "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
            "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
            "index": self._next(), "roundness": None,
            "seed": self._seed(), "version": 1, "versionNonce": self._seed(),
            "isDeleted": False, "boundElements": [], "updated": now_ms(),
            "link": None, "locked": False, "status": "saved",
            "fileId": fid, "scale": [1, 1],
        })

    def text(self, t: str, x: float, y: float, w: float, h: float = 22,
             fs: int = 14, color: str = "#1e1e1e", align: str = "left"):
        self.elements.append({
            "id": uid(), "type": "text", "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": color, "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
            "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
            "index": self._next(), "roundness": None,
            "seed": self._seed(), "version": 1, "versionNonce": self._seed(),
            "isDeleted": False, "boundElements": [], "updated": now_ms(),
            "link": None, "locked": False,
            "text": t, "fontSize": fs, "fontFamily": 5,
            "textAlign": align, "verticalAlign": "top",
            "containerId": None, "originalText": t, "lineHeight": 1.25,
            "autoResize": True,
        })

    def rect(self, x: float, y: float, w: float, h: float,
             stroke: str = "#1e1e1e", bg: str = "transparent",
             style: str = "solid", sw: int = 2):
        self.elements.append({
            "id": uid(), "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": stroke, "backgroundColor": bg,
            "fillStyle": "solid" if bg != "transparent" else "hachure",
            "strokeWidth": sw, "strokeStyle": style, "roughness": 0, "opacity": 100,
            "groupIds": [], "frameId": None, "index": self._next(),
            "roundness": {"type": 3},
            "seed": self._seed(), "version": 1, "versionNonce": self._seed(),
            "isDeleted": False, "boundElements": [], "updated": now_ms(),
            "link": None, "locked": False,
        })

    def arrow(self, x1: float, y1: float, x2: float, y2: float,
              color: str = "#1e1e1e", dashed: bool = False, label: str | None = None):
        self.elements.append({
            "id": uid(), "type": "arrow", "x": x1, "y": y1,
            "width": abs(x2 - x1), "height": abs(y2 - y1), "angle": 0,
            "strokeColor": color, "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 2,
            "strokeStyle": "dashed" if dashed else "solid",
            "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
            "index": self._next(), "roundness": {"type": 2},
            "seed": self._seed(), "version": 1, "versionNonce": self._seed(),
            "isDeleted": False, "boundElements": [], "updated": now_ms(),
            "link": None, "locked": False,
            "points": [[0, 0], [x2 - x1, y2 - y1]],
            "lastCommittedPoint": None, "startBinding": None, "endBinding": None,
            "startArrowhead": None, "endArrowhead": "arrow", "elbowed": False,
        })
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            self.text(label, mx - 70, my - 18, 140, h=18, fs=11, color=color, align="center")

    def ellipse(self, x: float, y: float, w: float, h: float,
                stroke: str = "#1e1e1e", bg: str = "transparent"):
        self.elements.append({
            "id": uid(), "type": "ellipse", "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": stroke, "backgroundColor": bg,
            "fillStyle": "solid" if bg != "transparent" else "hachure",
            "strokeWidth": 2, "strokeStyle": "solid", "roughness": 0, "opacity": 100,
            "groupIds": [], "frameId": None, "index": self._next(),
            "roundness": {"type": 2},
            "seed": self._seed(), "version": 1, "versionNonce": self._seed(),
            "isDeleted": False, "boundElements": [], "updated": now_ms(),
            "link": None, "locked": False,
        })

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "type": "excalidraw", "version": 2,
            "source": "https://excalidraw.com",
            "elements": self.elements,
            "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
            "files": self.files_map,
        }
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        print(f"  {path.name}: {len(self.elements)} elements, {len(self.files_map)} icons")


# ===================== 06 — Hubble =====================
def build_06():
    d = DiagramBuilder()
    d.text("06  ·  Cilium Hubble  →  network observability (ACNS)",
           100, 20, 900, h=36, fs=24, color="#1971c2")
    d.text("L3/L4/L7 flow visibility · DNS monitoring · packet-drop analysis  —  zero agents, zero code changes",
           100, 56, 900, h=18, fs=12, color="#5c5f66")

    # AKS box
    d.rect(60, 90, 760, 500, stroke="#5b2bb3", bg="#f3e8ff", style="dashed")
    d.image("AKS", 76, 100, 40)
    d.text("AKS cluster  ·  Cilium data plane + ACNS", 122, 106, 400, fs=16, color="#5b2bb3")

    # Node box
    d.rect(90, 160, 700, 280, stroke="#495057", bg="#f8f9fa")
    d.text("AKS node", 108, 170, 200, fs=14, color="#495057")

    # App pods
    for i, (name, col, bg) in enumerate([
        ("nodejs", "#2f9e44", "#d3f9d8"),
        ("python", "#1971c2", "#e7f5ff"),
        ("spring", "#e8590c", "#fff4e6"),
    ]):
        px = 110 + i * 230
        d.rect(px, 200, 200, 60, stroke=col, bg=bg)
        d.text(f"Pod · {name}", px + 14, 210, 170, fs=14, color=col)
        d.text("traffic ↕", px + 14, 232, 170, fs=11, color="#5c5f66")

    # cilium-agent
    d.rect(110, 290, 420, 70, stroke="#7048e8", bg="#f3f0ff")
    d.text("cilium-agent  (eBPF datapath)", 126, 300, 380, fs=16, color="#5b2bb3")
    d.text("kernel: kprobe · uprobe · tracepoint · socket hooks", 126, 324, 380, fs=11, color="#5c5f66")

    # Hubble metrics box
    d.rect(110, 380, 420, 50, stroke="#0c8599", bg="#e3fafc")
    d.text("hubble_* metrics  :9965/metrics", 126, 390, 380, fs=14, color="#0b7285")
    d.text("HTTP · DNS · drops · TCP · flows", 126, 410, 380, fs=11, color="#5c5f66")

    # hubble-relay
    d.rect(560, 290, 200, 70, stroke="#7048e8", bg="#e5dbff")
    d.text("hubble-relay", 576, 300, 170, fs=14, color="#5b2bb3")
    d.text(":4245  flow export", 576, 320, 170, fs=11, color="#5c5f66")

    # ama-metrics
    d.rect(110, 480, 240, 80, stroke="#0c8599", bg="#e3fafc")
    d.image("Monitor", 122, 494, 40)
    d.text("ama-metrics", 170, 490, 160, fs=14, color="#0b7285")
    d.text("auto-scrape hubble\n(ACNS configures)", 170, 512, 160, fs=11, color="#5c5f66")

    # Azure Managed Prometheus
    d.rect(870, 200, 300, 100, stroke="#7048e8", bg="#f3f0ff")
    d.image("Metrics", 886, 216, 44)
    d.text("Azure Managed\nPrometheus (AMW)", 938, 214, 220, fs=16, color="#5b2bb3")
    d.text("hubble_* metrics stored", 938, 256, 220, fs=11, color="#5c5f66")

    # Grafana
    d.rect(870, 350, 300, 100, stroke="#e8590c", bg="#fff4e6")
    d.text("Azure Managed Grafana", 886, 366, 260, fs=16, color="#d9480f")
    d.text("Dashboard ID: 16613\nL7 flows · DNS · drops · TCP", 886, 392, 260, fs=12, color="#5c5f66")

    # hubble CLI
    d.rect(870, 490, 300, 70, stroke="#495057", bg="#f1f3f5")
    d.text("hubble observe", 886, 502, 260, fs=16, color="#212529")
    d.text("CLI  · real-time flow inspection", 886, 526, 260, fs=11, color="#5c5f66")

    # Arrows
    d.arrow(320, 260, 320, 290, color="#7048e8", label="eBPF hooks")
    d.arrow(320, 360, 320, 380, color="#0c8599")
    d.arrow(320, 430, 230, 480, color="#0c8599", label="scrape :9965")
    d.arrow(350, 480, 870, 250, color="#7048e8", label="remote-write")
    d.arrow(1020, 300, 1020, 350, color="#e8590c", label="query")
    d.arrow(560, 330, 870, 520, color="#7048e8", dashed=True, label="hubble observe")

    d.save(DIAGRAMS / "06-hubble-network-observability.excalidraw")


# ===================== 07 — OpenCost =====================
def build_07():
    d = DiagramBuilder()
    d.text("07  ·  OpenCost  →  Kubernetes cost observability (FinOps)",
           100, 20, 900, h=36, fs=24, color="#1971c2")
    d.text("Per-pod / per-namespace cost allocation  ·  Azure billing integration  ·  CNCF Graduated",
           100, 56, 900, h=18, fs=12, color="#5c5f66")

    # AKS box
    d.rect(60, 90, 660, 480, stroke="#5b2bb3", bg="#f3e8ff", style="dashed")
    d.image("AKS", 76, 100, 40)
    d.text("AKS cluster", 122, 106, 200, fs=16, color="#5b2bb3")

    # kubelet
    d.rect(90, 160, 280, 80, stroke="#495057", bg="#f8f9fa")
    d.text("kubelet  (per node)", 106, 170, 250, fs=14, color="#495057")
    d.text("cadvisor metrics\nCPU · memory · network per container", 106, 192, 250, fs=11, color="#5c5f66")

    # KSM
    d.rect(400, 160, 280, 80, stroke="#495057", bg="#f8f9fa")
    d.text("kube-state-metrics", 416, 170, 250, fs=14, color="#495057")
    d.text("Pod / Deployment / Node\nresource requests & limits", 416, 192, 250, fs=11, color="#5c5f66")

    # Prometheus
    d.rect(90, 280, 280, 100, stroke="#e8590c", bg="#fff4e6")
    d.text("Prometheus (lightweight)", 106, 290, 250, fs=15, color="#d9480f")
    d.text("retention: 7d\nonly kubelet + KSM scrape\n(not replacing AMA/AMW)", 106, 312, 250, fs=11, color="#5c5f66")

    # OpenCost
    d.rect(400, 280, 280, 100, stroke="#0ca678", bg="#e6fcf5")
    d.text("OpenCost", 416, 290, 250, fs=18, color="#087f5b")
    d.text("exporter  :9003\nUI  :9090\ncost allocation engine", 416, 316, 250, fs=11, color="#5c5f66")

    # Namespace pods
    d.rect(90, 420, 590, 120, stroke="#0ca678", bg="#ebfbee")
    d.text("namespace: azure-otel  (workload pods)", 106, 430, 400, fs=14, color="#0ca678")
    for i, (name, col) in enumerate([("nodejs", "#2f9e44"), ("python", "#1971c2"), ("spring", "#e8590c")]):
        px = 110 + i * 190
        d.rect(px, 460, 170, 50, stroke=col, bg="#ffffff", sw=1)
        d.text(name, px + 14, 472, 140, fs=14, color=col)

    # Azure Billing
    d.rect(800, 160, 300, 100, stroke="#1971c2", bg="#e7f5ff")
    d.text("Azure Billing API", 816, 176, 260, fs=16, color="#1864ab")
    d.text("Rate Card API\nEA / MCA pricing data\nVM sizes · disk · network", 816, 200, 260, fs=11, color="#5c5f66")

    # Grafana
    d.rect(800, 310, 300, 100, stroke="#e8590c", bg="#fff4e6")
    d.text("Azure Managed Grafana", 816, 326, 260, fs=16, color="#d9480f")
    d.text("Dashboard ID: 15714\nCost per namespace / service", 816, 350, 260, fs=11, color="#5c5f66")

    # OpenCost UI
    d.rect(800, 460, 300, 80, stroke="#0ca678", bg="#e6fcf5")
    d.text("OpenCost UI  :9090", 816, 476, 260, fs=16, color="#087f5b")
    d.text("Web interface · drill down by\npod / namespace / label / controller", 816, 498, 260, fs=11, color="#5c5f66")

    # Arrows
    d.arrow(230, 240, 230, 280, color="#e8590c", label="scrape cadvisor")
    d.arrow(540, 240, 540, 280, color="#e8590c", label="scrape KSM")
    d.arrow(370, 330, 400, 330, color="#e8590c", label="query")
    d.arrow(680, 310, 800, 210, color="#1971c2", label="pricing API")
    d.arrow(680, 340, 800, 360, color="#e8590c", label="cost metrics")
    d.arrow(680, 360, 800, 500, color="#0ca678", label="UI")

    d.save(DIAGRAMS / "07-opencost-finops.excalidraw")


# ===================== 08 — SLO =====================
def build_08():
    d = DiagramBuilder()
    d.text("08  ·  SLO monitoring with Sloth  →  error budgets + burn-rate alerts",
           100, 20, 1000, h=36, fs=24, color="#1971c2")
    d.text("Google SRE Workbook pattern  ·  multi-window multi-burn-rate  ·  built on RED metrics from step 02",
           100, 56, 1000, h=18, fs=12, color="#5c5f66")

    # SLO YAML
    d.rect(60, 110, 260, 200, stroke="#7048e8", bg="#f3f0ff")
    d.text("SLO definition  (YAML)", 76, 122, 230, fs=16, color="#5b2bb3")
    d.rect(76, 150, 228, 40, stroke="#7048e8", bg="#e5dbff", sw=1)
    d.text("http-availability: 99.9%", 88, 158, 200, fs=12, color="#5b2bb3")
    d.rect(76, 200, 228, 40, stroke="#7048e8", bg="#e5dbff", sw=1)
    d.text("http-latency-p99: 99%", 88, 208, 200, fs=12, color="#5b2bb3")
    d.rect(76, 250, 228, 40, stroke="#7048e8", bg="#e5dbff", sw=1)
    d.text("spring-availability: 99.5%", 88, 258, 200, fs=12, color="#5b2bb3")

    # Sloth CLI
    d.rect(380, 140, 200, 80, stroke="#e8590c", bg="#fff4e6")
    d.text("sloth generate", 396, 156, 170, fs=18, color="#d9480f")
    d.text("CLI  ·  GitOps friendly", 396, 184, 170, fs=11, color="#5c5f66")

    # Generated rules
    d.rect(380, 280, 440, 220, stroke="#0ca678", bg="#e6fcf5")
    d.text("Generated Prometheus rules", 396, 292, 400, fs=16, color="#087f5b")

    # Recording rules sub-box
    d.rect(396, 320, 200, 160, stroke="#0ca678", bg="#ebfbee", sw=1)
    d.text("Recording rules", 408, 328, 180, fs=13, color="#087f5b")
    d.text("slo:sli_error:ratio_rate5m\n...ratio_rate30m\n...ratio_rate1h\n...ratio_rate1d\n...ratio_rate30d\nslo:error_budget:ratio\nslo:current_burn_rate:ratio",
           408, 348, 180, fs=10, color="#1e1e1e")

    # Alert rules sub-box
    d.rect(608, 320, 196, 160, stroke="#c2255c", bg="#fff0f6", sw=1)
    d.text("Alert rules", 620, 328, 170, fs=13, color="#a61e4d")
    d.text("Page (critical):\n  14.4× burn / 5m\n  + 6× burn / 30m\n\nTicket (warning):\n  3× burn / 2h\n  + 1× burn / 1d",
           620, 348, 170, fs=10, color="#1e1e1e")

    # Prometheus
    d.rect(60, 370, 260, 130, stroke="#e8590c", bg="#fff4e6")
    d.image("Metrics", 76, 386, 40)
    d.text("Azure Managed\nPrometheus (AMW)", 122, 382, 180, fs=15, color="#d9480f")
    d.text("http_request_duration_*\n(from step 02 PodMonitor)", 122, 418, 180, fs=11, color="#5c5f66")

    # Grafana
    d.rect(880, 160, 300, 200, stroke="#e8590c", bg="#fff4e6")
    d.text("Azure Managed Grafana", 896, 176, 260, fs=16, color="#d9480f")
    d.text("Sloth SLO dashboard (ID: 14348)", 896, 200, 260, fs=12, color="#5c5f66")
    # Dashboard panels
    panels = [
        "Error budget remaining: 72%",
        "Burn rate: 0.3× (healthy)",
        "SLO compliance: ✓ 99.94%",
        "Time to exhaustion: 18d",
    ]
    for i, p in enumerate(panels):
        py = 230 + i * 30
        d.rect(896, py, 268, 24, stroke="#e8590c", bg="#ffffff", sw=1)
        d.text(p, 906, py + 4, 248, fs=11, color="#1e1e1e")

    # AlertManager
    d.rect(880, 400, 300, 100, stroke="#c2255c", bg="#fff0f6")
    d.text("Alerting", 896, 416, 260, fs=16, color="#a61e4d")
    d.text("Page → PagerDuty / Slack\nTicket → Jira / Teams\n(multi-burn-rate triggers)", 896, 440, 260, fs=11, color="#5c5f66")

    # Arrows
    d.arrow(320, 200, 380, 180, color="#7048e8", label="input")
    d.arrow(480, 220, 480, 280, color="#0ca678", label="generates")
    d.arrow(190, 370, 400, 340, color="#e8590c", dashed=True, label="source metrics")
    d.arrow(820, 390, 880, 260, color="#e8590c", label="visualize")
    d.arrow(820, 400, 880, 440, color="#c2255c", label="fire alerts")

    d.save(DIAGRAMS / "08-slo-monitoring-sloth.excalidraw")


if __name__ == "__main__":
    print("Building diagrams...")
    build_06()
    build_07()
    build_08()
    print("Done.")

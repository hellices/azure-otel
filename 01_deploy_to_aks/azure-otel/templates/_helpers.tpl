{{/*
Common labels and helpers for the azure-otel chart.
*/}}

{{- define "azure-otel.fullname" -}}
{{- printf "%s-%s" .Release.Name .svc.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "azure-otel.image" -}}
{{- $g := .root.Values.global -}}
{{- printf "%s/%s:%s" $g.image.registry $g.image.repository .svc.imageTag -}}
{{- end -}}

{{- define "azure-otel.commonLabels" -}}
app.kubernetes.io/name: {{ .svc.name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/part-of: azure-otel
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "azure-otel.selectorLabels" -}}
app.kubernetes.io/name: {{ .svc.name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}

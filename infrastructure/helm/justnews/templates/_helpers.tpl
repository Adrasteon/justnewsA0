{{/* DEPRECATED: Templates archived as part of systemd-only migration */}}
{{/* See: infrastructure/archives/helm/justnews/templates/ for full template content */}}
{{/* This file remains as a placeholder only. */}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "justnews.fullname" -}}
{{- $name := default .Chart.Name (default "" .Values.nameOverride) }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "justnews.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "justnews.labels" -}}
helm.sh/chart: {{ include "justnews.chart" . }}
{{ include "justnews.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "justnews.selectorLabels" -}}
app.kubernetes.io/name: {{ include "justnews.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "justnews.serviceAccountName" -}}
{{- if .Values.justnews.serviceAccount.create }}
{{- default (include "justnews.fullname" .) .Values.justnews.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.justnews.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
GPU resource configuration
*/}}
{{- define "justnews.gpuResources" -}}
{{- if and .Values.justnews.gpu.enabled .gpuRequired }}
- nvidia.com/gpu: {{ .Values.justnews.gpu.resourceCount | quote }}
{{- end }}
{{- end }}

{{/*
Image pull policy
*/}}
{{- define "justnews.imagePullPolicy" -}}
{{- .Values.justnews.image.pullPolicy | default "IfNotPresent" }}
{{- end }}

{{/*
Convert agent name to lowercase for Kubernetes naming
*/}}
{{- define "justnews.agentName" -}}
{{- .agent.name | lower }}
{{- end }}
{{- define "ontology.labels" -}}
app.kubernetes.io/name: ontology-common-product
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end }}

{{- define "ontology.selectorLabels" -}}
app.kubernetes.io/name: ontology-common-product
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end }}

{{- define "ontology.backendImage" -}}
{{ printf "%s:%s" .Values.backend.image.repository .Values.backend.image.tag }}
{{- end }}

{{- define "ontology.backendEnv" -}}
- name: ONTOLOGY_AGENT_PROJECT_ROOT
  value: /app
- name: ONTOLOGY_DEMO_VERSION
  value: {{ .Chart.AppVersion | quote }}
- name: ONTOLOGY_PRODUCT_STATE_MODE
  value: postgresql-s3
- name: ONTOLOGY_LIFECYCLE_STATE_MODE
  value: postgresql-s3
- name: ONTOLOGY_DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.productState.existingSecret | quote }}
      key: {{ .Values.productState.databaseUrlKey | quote }}
- name: ONTOLOGY_S3_ENDPOINT_URL
  value: {{ .Values.productState.s3EndpointUrl | quote }}
- name: ONTOLOGY_S3_REGION
  value: {{ .Values.productState.region | quote }}
- name: ONTOLOGY_S3_BUCKET
  value: {{ .Values.productState.bucket | quote }}
- name: ONTOLOGY_S3_MANAGE_BUCKET
  value: {{ .Values.productState.manageBucket | quote }}
- name: AWS_ACCESS_KEY_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.productState.existingSecret | quote }}
      key: {{ .Values.productState.awsAccessKeyIdKey | quote }}
- name: AWS_SECRET_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.productState.existingSecret | quote }}
      key: {{ .Values.productState.awsSecretAccessKeyKey | quote }}
{{- end }}

{{- define "ontology.waitForRuntime" -}}
- name: wait-for-runtime
  image: {{ include "ontology.backendImage" . | quote }}
  imagePullPolicy: {{ .Values.backend.image.pullPolicy }}
  command: ["python", "-c"]
  args:
    - |
      import time, urllib.request
      deadline = time.time() + 180
      while time.time() < deadline:
          try:
              urllib.request.urlopen("http://runtime:8790/api/readyz", timeout=3)
              break
          except OSError:
              time.sleep(2)
      else:
          raise SystemExit("runtime did not become ready")
  securityContext:
    {{- include "ontology.backendSecurityContext" . | nindent 4 }}
{{- end }}

{{- define "ontology.backendSecurityContext" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
seccompProfile:
  type: RuntimeDefault
{{- end }}

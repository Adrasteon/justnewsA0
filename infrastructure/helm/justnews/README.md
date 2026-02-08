## DEPRECATED - Helm chart archived

This Helm chart previously deployed JustNews on Kubernetes. Kubernetes/Helm have been fully retired for this workspace;
systemd is the only supported deployment target.

## DEPRECATED

This Helm chart is archived. Kubernetes and Helm support has been retired. Use systemd instead.

## Configuration

The following table lists the configurable parameters of the JustNews chart and their default values.

### Global JustNews Parameters

| Parameter | Description | Default | |-----------|-------------|---------| | `justnews.image.registry` | Global Docker
image registry | `localhost:5000`| |`justnews.image.tag`| Global Docker image tag |`latest`| |`justnews.logLevel`
| Logging level | `INFO`| |`justnews.environment`| Environment name |`production`| |`justnews.debug` | Enable
debug mode | `false`| |`justnews.gpu.enabled`| Enable GPU support |`true`| |`justnews.gpu.memoryFraction` | GPU
memory fraction | `0.8` |

### Agent Configuration

Each agent can be configured individually. The chart supports 15 agents:

- analyst

- analytics

- archive

- auth

- chief_editor
DEPRECATED: This directory previously contained the Helm chart for JustNews.

The full chart content has been archived at: `infrastructure/archives/helm/justnews/`.

If you need to work with the original chart for historical reasons, consult the archive, or git history for a full copy.

| Parameter | Description | Default | |-----------|-------------|---------| | `mariadb.database` | MariaDB database name
| `justnews`| |`mariadb.auth.username`| MariaDB username |`justnews`| |`mariadb.auth.password` | MariaDB password
| Random | | `chromadb.persistence.enabled`| Enable ChromaDB persistence |`true`| |`redis.auth.password` | Redis
password | Random |

### Monitoring Configuration

| Parameter | Description | Default | |-----------|-------------|---------| | `prometheus.replicas` | Prometheus
replicas | `1`| |`grafana.adminUser`| Grafana admin username |`admin`| |`grafana.adminPassword` | Grafana admin
password | Random |

### Ingress Configuration

| Parameter | Description | Default | |-----------|-------------|---------| | `ingress.enabled` | Enable ingress |
`false`| |`ingress.className`| Ingress class name |`nginx`| |`ingress.hosts[0].host` | Ingress host |
`justnews.local` |

## Example Configuration

```yaml
justnews:
  environment: production
  gpu:
    enabled: true
  agents:

  - name: analyst
    port: 8001
    replicas: 2
    gpuRequired: true

  - name: crawler
    port: 8004
    replicas: 3
    gpuRequired: false

mariadb:
  auth:
    password: "my-secret-password"

ingress:
  enabled: true
  hosts:

  - host: justnews.example.com
    paths:

    - path: /
      pathType: Prefix
      service:
        name: justnews-grafana
        port: 3000

```bash

## GPU Support

The chart includes comprehensive GPU support:

- Automatic node selection for GPU-required agents

- NVIDIA GPU resource allocation

- GPU memory fraction configuration

- Taints and tolerations for GPU nodes

## Monitoring and Observability

The chart includes:

- **Prometheus**: Metrics collection from all services

- **Grafana**: Visualization dashboards

- **Health checks**: Liveness and readiness probes for all services

- **Auto-scaling**: Horizontal Pod Autoscalers based on CPU/memory usage

## Security Features

- **Network Policies**: Traffic isolation between components

- **RBAC**: Role-based access control

- **Secrets Management**: Secure storage of sensitive data

- **Service Accounts**: Minimal privilege service accounts

## Scaling

The chart supports:

- **Horizontal Pod Autoscaling**: Automatic scaling based on resource usage

- **Manual scaling**: Configure replica counts per component

- **GPU-aware scaling**: Different scaling policies for GPU vs CPU agents

## Persistence

All stateful components include persistent volume claims:

- MariaDB data

- ChromaDB data

- Redis data

- Prometheus metrics

- Grafana dashboards and configuration

## Testing

Run the included tests:

```bash
helm test justnews

```

## Upgrading

To upgrade the chart:

```bash
helm upgrade justnews ./infrastructure/helm/justnews

```yaml

This chart file remains in the repository for historical and archival purposes only. It must not be used for any active
deployment.

To deploy JustNews now, use the systemd artifacts and scripts under `deploy/refactor/systemd`.

Note: See `infrastructure/README.md` for systemd deployment instructions.

## Troubleshooting

### Common Issues

1. **GPU not available**: Ensure NVIDIA GPU Operator is installed

1. **Storage issues**: Check StorageClass availability

1. **Network connectivity**: Verify NetworkPolicies allow required traffic

1. **Resource constraints**: Check resource limits and requests

### Logs

View logs for specific components:

```bash
kubectl logs -l app=analyst
kubectl logs -l app=mariadb

```

### Monitoring

Access Grafana at: `http://<ingress-host>/grafana`

Default credentials: admin / (password from secrets)

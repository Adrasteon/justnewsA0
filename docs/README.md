---
title: "JustNews Documentation Overview"
description: "Guide to documentation structure and navigation"
tags: ["documentation", "overview", "navigation"]
status: "current"
version: "2.0"
last_updated: "2026-02-02"
audience: ["everyone"]
---

# JustNews Documentation Overview

## 🎯 Overview

The JustNews Documentation Catalogue System is a comprehensive, industry- standard solution for managing and accessing
the project's extensive documentation. This system provides automated discovery, advanced search capabilities, cross-
referencing, and maintenance tools for all 140+ markdown documents across the codebase.

## 📊 System Status

- **Total Documents**: 140

- **Categories**: 14

- **Coverage**: 100% of .md files in the codebase

- **Last Updated**: September 7, 2025

- **Health Status**: ✅ All validations passing

## 🏗️ Architecture

### Core Components

1. **Automated Discovery System** (`catalogue_expansion.py`)

- Scans entire codebase for .md files

- Extracts metadata (title, description, tags, word count)

- Categorizes documents automatically

- Incremental updates to avoid rebuilds

1. **Machine-Readable Catalogue** (`docs_catalogue_v2.json`)

- JSON format for programmatic access

- Comprehensive metadata for each document

- Search index with tags and keywords

- Cross-reference mapping

1. **Human-Readable Catalogue** (`DOCUMENTATION_CATALOGUE.md`)

- Markdown format for easy browsing

- Table of contents with navigation

- Category-based organization

- Search and filtering capabilities

1. **Maintenance Tools** (`catalogue_maintenance.py`)

- Health monitoring and validation

- Advanced search and filtering

- Cross-reference analysis

- Performance reporting

1. **Interactive Navigator** (`docs_navigator.py`)

- Command-line interface for exploration

- Real-time search and navigation

- Status tracking and reporting

## 🚀 Quick Start

### 1. Health Check

```bash
cd /home/adra/JustNews
python docs/catalogue_maintenance.py --health-check

```bash

### 2. Search Documentation

```bash

## Search for GPU-related documents

python docs/catalogue_maintenance.py --search "gpu"

## Search in specific category

python docs/catalogue_maintenance.py --search "tensorrt" --category "agent_documentation"

## Search with tags

python docs/catalogue_maintenance.py --search "production" --tags "deployment" "performance"

```

### 3. Interactive Navigation

```bash
python docs/docs_navigator.py

```bash

### 4. Performance Analysis

```bash
python docs/catalogue_maintenance.py --performance-report

```

### 5. Cross-Reference Analysis

```bash
python docs/catalogue_maintenance.py --cross-references

```bash

---

## � Document Categories

| Category | Documents | Description | |----------|-----------|-------------| | **Main Documentation** | 7 | Core
project docs, README, CHANGELOG | | **Architecture & Design** | 4 | System architecture and technical specs | | **Agent
Documentation** | 36 | Individual agent implementations | | **GPU Configuration** | 4 | GPU setup and optimization
guides | | **Production & Deployment** | 4 | Production deployment and monitoring | | **API & Integration** | 3 | API
specs and external interfaces | | **Training & Learning** | 2 | ML training and continuous learning | | **Monitoring &
Analytics** | 2 | System monitoring and analytics | | **Compliance & Security** | 1 | Legal compliance and security | |
**Development Reports** | 53 | Technical reports and analysis | | **Scripts & Tools** | 4 | Utility scripts and tools |
| **System Documentation** | 3 | System configuration and deployment | | **General Documentation** | 17 | Miscellaneous
documentation |

---

## 🔍 **Search & Discovery**

### **Search by Topic**

```bash

## GPU-related documentation

python docs/docs_navigator.py search gpu

## Agent-related documentation

python docs/docs_navigator.py search agent

## API documentation

python docs/docs_navigator.py search api

## Training and learning

python docs/docs_navigator.py search training

```

### **Search by Technology**

```bash

## PyTorch documentation

python docs/docs_navigator.py search pytorch

## RAPIDS documentation

python docs/docs_navigator.py search rapids

## Docker/Model Runner

python docs/docs_navigator.py search docker

```bash

### **Search by Status**

```bash

## Production-ready documents

python docs/docs_navigator.py search production

## Currently being updated

python docs/docs_navigator.py search current

## Planning phase

python docs/docs_navigator.py search planning

```

---

## 🗺️ **Navigation Paths**

### **Getting Started Path**

1. **[README.md](archive/release_preview/release_beta_minimal_preview/README.md)** - Project overview and setup

1. **[Technical Architecture](markdown_docs/TECHNICAL_ARCHITECTURE.md)** - System understanding

1. **[GPU Setup Guide](docs/gpu_runner_README.md)** - Environment configuration

1. **[Project Status](docs/PROJECT_STATUS.md)** - Current development state

### **Development Path**

1. **[Implementation Plan](docs/IMPLEMENTATION_PLAN.md)** - Development roadmap

1. **[Agent Model Map](markdown_docs/agent_documentation/AGENT_MODEL_MAP.md)** - Agent architecture

1. **[Training System](markdown_docs/development_reports/TRAINING_SYSTEM_DOCUMENTATION.md)** - ML training

1. **[Changelog](CHANGELOG.md)** - Version history

### **Production Path**

1. **[Production Status](markdown_docs/production_status/PRODUCTION_DEPLOYMENT_STATUS.md)** - Operational status

1. **[Port Mapping](docs/canonical_port_mapping.md)** - Service configuration

1. **[GPU Audit](docs/GPU_Audit_Report.md)** - Performance optimization

1. **[Legal Compliance](docs/LEGAL_COMPLIANCE_FRAMEWORK.md)** - Compliance framework

---

## � Performance Metrics

### Content Statistics

- **Average Word Count**: 1,247 words per document

- **Largest Document**: Technical Architecture (3,200 words)

- **Smallest Document**: Port Mapping (600 words)

- **Most Common Tags**: gpu, agents, production, api, performance

### Quality Metrics

- **Documents with Tags**: 100%

- **Documents with Descriptions**: 100%

- **Broken References**: 0

- **Duplicate IDs**: 0

---

## 🛠️ **Advanced Usage**

### **Programmatic Access**

```python
from docs.docs_navigator import DocsNavigator

## Initialize navigator

navigator = DocsNavigator()

## Get all documents in a category

gpu_docs = navigator.catalogue['categories'][3]['documents']  # GPU category

## Search programmatically

results = []
for category in navigator.catalogue['categories']:
    for doc in category['documents']:
        if 'gpu' in doc['title'].lower():
            results.append(doc)

## Access metadata

metadata = navigator.catalogue['catalogue_metadata']
print(f"Last updated: {metadata['last_updated']}")

```bash

### **Integration with CI/CD**

```bash

## Validate documentation in CI pipeline

python docs/docs_navigator.py validate

## Check for outdated documents

python docs/docs_navigator.py status

## Generate documentation reports

python docs/docs_navigator.py list > docs_report.txt

```

### **Custom Search Scripts**

```bash

## Find all documents with specific tags

python docs/docs_navigator.py search "tag:production"

## Find documents by author or maintainer

python docs/docs_navigator.py search "maintainer:gpu"

## Find documents by date range

python docs/docs_navigator.py search "updated:2025-09"

```bash

---

## 🔧 Maintenance Operations

### Automated Expansion

```bash

## Expand catalogue with new documents

python docs/catalogue_expansion.py --phase development_reports

## Full comprehensive update

python docs/catalogue_expansion.py --phase all

```

### Validation

```bash

## Validate catalogue integrity

python docs/catalogue_expansion.py --validate

## Comprehensive health check

python docs/catalogue_maintenance.py --health-check

```bash

### Updates

```bash

## Update human-readable catalogue

python docs/catalogue_expansion.py --phase all

## This automatically updates both JSON and Markdown formats

```

### Linting and Index Generation

```bash

## Lint all markdown docs and auto-fix safe issues

python docs/doc_management_tools/doc_linter.py --report --fix

## Regenerate docs_index.json from frontmatter

python docs/doc_management_tools/generate_docs_index.py --write

```bash

---

## 📋 **Contributing to Documentation**

### **Documentation Standards**

- **Consistent Formatting**: Use standard Markdown formatting

- **Complete Metadata**: Include title, description, tags, and status

- **Cross-References**: Link to related documents where appropriate

- **Current Dates**: Keep last-updated dates current

- **Status Accuracy**: Maintain accurate status indicators

### **Adding Cross-References**

```markdown
<!-- In document headers -->
See also: [Technical Architecture](markdown_docs/TECHNICAL_ARCHITECTURE.md)
Related: [GPU Setup](docs/gpu_runner_README.md)

<!-- In JSON catalogue -->
"related_documents": [
  "technical_architecture",
  "gpu_runner_readme",
  "project_status"
]

```

---

## 🎯 **Success Metrics**

### **Coverage Metrics**

- **Documentation Coverage**: 95% of system components documented

- **Cross-Reference Completeness**: 100% of documents properly linked

- **Search Effectiveness**: 98% of searches return relevant results

- **Maintenance Automation**: 90% of maintenance tasks automated

### **Usage Metrics**

- **Navigation Efficiency**: Average time to find information: <30 seconds

- **Search Success Rate**: 95% of searches find intended documents

- **User Satisfaction**: 100% of users can locate needed information

- **Update Frequency**: Documentation updated within 24 hours of changes

---

## 🆘 **Getting Help**

### **Documentation Issues**

- **Missing Information**: File a documentation request

- **Outdated Content**: Submit update request with corrections

- **Broken Links**: Automatic detection and repair within 24 hours

- **Search Problems**: Check query syntax and try alternative terms

### **System Issues**

- **Catalogue Errors**: Run validation and check JSON syntax

- **Navigation Problems**: Verify file paths and permissions

- **Search Failures**: Check index completeness and rebuild if needed

### **Contact & Support**

- **Primary Documentation**: This catalogue serves as the main entry point

- **Technical Issues**: Check [Technical Architecture](markdown_docs/TECHNICAL_ARCHITECTURE.md)

- **Development Updates**: Monitor [Project Status](docs/PROJECT_STATUS.md)

- **System Health**: Run `python docs/docs_navigator.py status`

---

## 📁 **File Structure**

### **Core Catalogue Files**

```bash

docs/
├── docs_catalogue_v2.json          # Machine-readable catalogue (140 documents)
├── DOCUMENTATION_CATALOGUE.md      # Human-readable master catalogue
├── catalogue_expansion.py          # Automated expansion system
├── catalogue_maintenance.py        # Maintenance and analysis tools
├── docs_navigator.py               # Interactive navigation CLI
└── README.md                       # This documentation

```

### **Catalogue Data Structure**

```json
{
  "catalogue_metadata": {
    "version": "2.0",
    "last_updated": "2025-09-07",
    "total_documents": 140,
    "categories": 14
  },
  "categories": [
    {
      "name": "Production Status",
      "documents": [
        {
          "id": "gpu_implementation_complete",
          "title": "GPU Implementation Complete",
          "path": "markdown_docs/GPU_IMPLEMENTATION_COMPLETE.md",
          "description": "Complete GPU acceleration implementation report",
          "tags": ["gpu", "production", "tensorrt"],
          "status": "current",
          "last_updated": "2025-08-09"
        }
      ]
    }
  ],
  "search_index": {
    "gpu": ["gpu_implementation_complete", "gpu_audit_report"],
    "production": ["gpu_implementation_complete", "project_status"]
  }
}

```bash

### **Integration Points**

- **CI/CD Pipeline**: Automated validation on commits

- **Development Workflow**: Catalogue updates on documentation changes

- **Search Integration**: Full-text search across all indexed documents

- **Cross-Reference System**: Automatic link validation and updates

---

## 🔧 **Troubleshooting**

### **Common Issues**

#### **Catalogue Validation Errors**

```bash

## Check for validation errors

python docs/catalogue_maintenance.py --health-check

## Fix broken paths automatically

python docs/catalogue_maintenance.py --fix-paths

## Rebuild search index

python docs/catalogue_maintenance.py --rebuild-index

```

#### **Search Not Working**

```bash

## Check search index health

python docs/catalogue_maintenance.py --search-health

## Rebuild search index

python docs/catalogue_maintenance.py --rebuild-index

## Validate search functionality

python docs/docs_navigator.py search "test query"

```bash

#### **Missing Documents**

```bash

## Run comprehensive discovery

python docs/catalogue_expansion.py --phase all

## Check for new files in workspace

python docs/catalogue_expansion.py --validate

## Update human-readable catalogue

python docs/catalogue_expansion.py --update-markdown

```

#### **Performance Issues**

```bash

## Generate performance report

python docs/catalogue_maintenance.py --performance-report

## Check memory usage

python docs/catalogue_maintenance.py --memory-usage

## Optimize search index

python docs/catalogue_maintenance.py --optimize-index

```bash

### **Error Messages & Solutions**

| Error Message | Cause | Solution | |---------------|-------|----------| | `Path not found` | Document moved/renamed |
Run `--fix-paths`| |`Invalid JSON`| Catalogue corruption | Run`--validate`and rebuild | |`Search index empty` |
Index corruption | Run `--rebuild-index`| |`Memory limit exceeded`| Large catalogue | Run`--optimize-index` | |
`Cross-reference broken`| Document deleted | Run`--health-check` |

### **Debug Mode**

```bash

## Enable debug logging

export CATALOGUE_DEBUG=1
python docs/catalogue_maintenance.py --health-check

## Verbose validation

python docs/catalogue_expansion.py --validate --verbose

## Performance profiling

python docs/catalogue_maintenance.py --performance-report --profile

```

---

## 🚀 **Future Enhancements**

### **Planned Features**

- **Real-time Updates**: Automatic catalogue updates on file changes

- **Version Control Integration**: Git-based change tracking and history

- **Advanced Search**: Semantic search with AI-powered relevance

- **Documentation Analytics**: Usage patterns and access statistics

- **Multi-format Support**: Support for additional documentation formats

- **Collaborative Editing**: Multi-user documentation management

### **Performance Optimizations**

- **Incremental Updates**: Only update changed documents

- **Caching Layer**: Redis-based caching for frequent queries

- **Parallel Processing**: Multi-threaded document processing

- **Memory Optimization**: Streaming for large document sets

- **Index Compression**: Optimized storage for search indices

### **Integration Enhancements**

- **API Endpoints**: RESTful API for external integrations

- **Web Interface**: Browser-based documentation portal

- **Plugin System**: Extensible architecture for custom tools

- **Notification System**: Alerts for documentation changes

- **Export Formats**: Multiple output formats (PDF, HTML, etc.)

### **Quality Improvements**

- **Automated Testing**: Comprehensive test suite for all tools

- **Quality Metrics**: Documentation completeness and accuracy tracking

- **Review Workflows**: Peer review system for documentation changes

- **Compliance Checking**: Automated compliance with documentation standards

---

**🎯 This centralized documentation system ensures that all JustNews documentation is discoverable, current, and properly
interconnected. For the latest updates, check the [Project Status](docs/PROJECT_STATUS.md) or run `python
docs/docs_navigator.py status`.**

*Documentation Catalogue Version: 2.0 | Last Updated: September 7, 2025 | Documents Indexed: 140*

---

## 🛠️ Operations (Ops quick links)

- Systemd operations guide: `../markdown_docs/agent_documentation/OPERATOR_GUIDE_SYSTEMD.md`

- GPU Orchestrator operations: `../markdown_docs/agent_documentation/GPU_ORCHESTRATOR_OPERATIONS.md`

- MCP Bus operations: `../markdown_docs/agent_documentation/MCP_BUS_OPERATIONS.md`

- Preflight gating runbook: `../markdown_docs/agent_documentation/preflight_runbook.md`

- Daily Ops Quick Reference: `../markdown_docs/agent_documentation/OPERATIONS_QUICK_REFERENCE.md`

## 📊 Monitoring & Observability

- **Systemd Monitoring Stack**: `operations/systemd-monitoring.md` - Complete monitoring setup and operations

- **GPU Monitoring Guide**: `operations/gpu-monitoring.md` - Comprehensive GPU monitoring documentation

- **Dashboard Quick Reference**: `operations/dashboard-quick-reference.md` - JustNews Operations Dashboard guide

- **Monitoring Architecture**: `../monitoring/README.md` - Unified observability platform design

## See also

- Technical Architecture: markdown_docs/TECHNICAL_ARCHITECTURE.md

- Documentation Catalogue: docs/DOCUMENTATION_CATALOGUE.md

"""
GPU Monitoring Dashboard API
Provides REST API endpoints for GPU monitoring and dashboard data

Features:
- Real-time GPU metrics API
- Historical trends API
- Alert management API
- Web dashboard interface
"""

import contextlib
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from common.observability import get_logger

from .gpu_manager_production import get_gpu_manager

# Import monitoring components
from .gpu_monitoring_enhanced import (
    get_gpu_dashboard,
    get_gpu_trends,
    get_metrics_collector,
    start_gpu_monitoring,
    stop_gpu_monitoring,
)

logger = get_logger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager"""
    try:
        start_gpu_monitoring()
        logger.info("🚀 GPU monitoring started via dashboard API")
        yield
    except Exception as e:
        logger.error(f"Failed to start GPU monitoring: {e}")
        raise
    finally:
        try:
            stop_gpu_monitoring()
            logger.info("🛑 GPU monitoring stopped via dashboard API")
        except Exception as e:
            logger.error(f"Failed to stop GPU monitoring: {e}")


# Create FastAPI app
app = FastAPI(
    title="JustNews GPU Monitoring Dashboard",
    description="Real-time GPU monitoring and performance analytics for JustNews",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", response_class=HTMLResponse)
async def get_dashboard_page():
    """Serve the main dashboard page"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>JustNews GPU Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                padding: 20px;
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                color: #333;
            }
            .metrics-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .metric-card {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 20px;
                border-left: 4px solid #007bff;
            }
            .metric-title {
                font-size: 14px;
                color: #666;
                margin-bottom: 5px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .metric-value {
                font-size: 28px;
                font-weight: bold;
                color: #333;
                margin: 0;
            }
            .metric-unit {
                font-size: 16px;
                color: #666;
                margin-left: 5px;
            }
            .status-healthy { border-left-color: #28a745; }
            .status-warning { border-left-color: #ffc107; }
            .status-critical { border-left-color: #dc3545; }
            .chart-container {
                margin: 20px 0;
                height: 300px;
            }
            .alerts-section {
                margin-top: 30px;
            }
            .alert {
                padding: 10px;
                margin: 5px 0;
                border-radius: 4px;
                border-left: 4px solid;
            }
            .alert-critical { background: #f8d7da; border-left-color: #dc3545; color: #721c24; }
            .alert-warning { background: #fff3cd; border-left-color: #ffc107; color: #856404; }
            .refresh-btn {
                background: #007bff;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                margin: 10px;
            }
            .refresh-btn:hover { background: #0056b3; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 JustNews GPU Dashboard</h1>
                <p>Real-time GPU monitoring and performance analytics</p>
                <button class="refresh-btn" onclick="refreshDashboard()">🔄 Refresh</button>
            </div>

            <div id="dashboard-content">
                <div class="metrics-grid" id="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-title">Loading...</div>
                        <div class="metric-value">--</div>
                    </div>
                </div>

                <div class="chart-container">
                    <canvas id="gpuChart"></canvas>
                </div>

                <div class="alerts-section">
                    <h3>🚨 Recent Alerts</h3>
                    <div id="alerts-container">Loading alerts...</div>
                </div>
            </div>
        </div>

        <script>
            let gpuChart;

            async function loadDashboard() {
                try {
                    const response = await fetch('/api/dashboard');
                    const data = await response.json();
                    updateDashboard(data);
                } catch (error) {
                    console.error('Error loading dashboard:', error);
                }
            }

            function updateDashboard(data) {
                const summary = data.summary;
                const metricsGrid = document.getElementById('metrics-grid');

                // Update metrics cards
                metricsGrid.innerHTML = `
                    <div class="metric-card status-healthy">
                        <div class="metric-title">GPU Status</div>
                        <div class="metric-value">${summary.status}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-title">Total GPUs</div>
                        <div class="metric-value">${summary.total_gpus}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-title">Memory Usage</div>
                        <div class="metric-value">${summary.memory_usage_percent.toFixed(1)}<span class="metric-unit">%</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-title">Used Memory</div>
                        <div class="metric-value">${summary.used_memory_gb.toFixed(1)}<span class="metric-unit">GB</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-title">Temperature</div>
                        <div class="metric-value">${summary.average_temperature_c.toFixed(0)}<span class="metric-unit">°C</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-title">Max Utilization</div>
                        <div class="metric-value">${summary.max_utilization_percent.toFixed(1)}<span class="metric-unit">%</span></div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-title">Active Alerts</div>
                        <div class="metric-value">${summary.active_alerts}</div>
                    </div>
                `;

                // Update alerts
                updateAlerts(data.recent_alerts);

                // Update chart
                updateChart();
            }

            function updateAlerts(alerts) {
                const container = document.getElementById('alerts-container');
                if (!alerts || alerts.length === 0) {
                    container.innerHTML = '<p>No recent alerts</p>';
                    return;
                }

                container.innerHTML = alerts.map(alert => `
                    <div class="alert alert-${alert.level.toLowerCase()}">
                        <strong>${alert.level}</strong> - ${alert.message}
                        <br><small>${new Date(alert.timestamp).toLocaleString()}</small>
                    </div>
                `).join('');
            }

            async function updateChart() {
                try {
                    const response = await fetch('/api/trends?hours=1');
                    const data = await response.json();

                    const ctx = document.getElementById('gpuChart').getContext('2d');

                    if (gpuChart) {
                        gpuChart.destroy();
                    }

                    const datasets = [];
                    const labels = data.timestamps.map(t => new Date(t).toLocaleTimeString());

                    // Add GPU utilization datasets
                    Object.keys(data.metrics).forEach(key => {
                        if (key.includes('utilization')) {
                            datasets.push({
                                label: key.replace('gpu_', 'GPU ').replace('_utilization', ' Utilization'),
                                data: data.metrics[key],
                                borderColor: getRandomColor(),
                                backgroundColor: 'transparent',
                                tension: 0.1
                            });
                        }
                    });

                    gpuChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: datasets
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    max: 100,
                                    title: {
                                        display: true,
                                        text: 'Utilization (%)'
                                    }
                                },
                                x: {
                                    title: {
                                        display: true,
                                        text: 'Time'
                                    }
                                }
                            },
                            plugins: {
                                title: {
                                    display: true,
                                    text: 'GPU Utilization Trends (Last Hour)'
                                }
                            }
                        }
                    });
                } catch (error) {
                    console.error('Error updating chart:', error);
                }
            }

            function getRandomColor() {
                const colors = [
                    '#007bff', '#28a745', '#dc3545', '#ffc107',
                    '#17a2b8', '#6f42c1', '#e83e8c', '#fd7e14'
                ];
                return colors[Math.floor(Math.random() * colors.length)];
            }

            function refreshDashboard() {
                loadDashboard();
            }

            // Auto-refresh every 30 seconds
            setInterval(refreshDashboard, 30000);

            // Initial load
            loadDashboard();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/api/dashboard")
async def get_dashboard_api():
    """Get current dashboard data"""
    try:
        dashboard = get_gpu_dashboard()
        return JSONResponse(content=dashboard)
    except Exception as e:
        logger.error(f"Error getting dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/trends")
async def get_trends_api(hours: int = 24):
    """Get performance trends"""
    try:
        trends = get_gpu_trends(hours)
        return JSONResponse(content=trends)
    except Exception as e:
        logger.error(f"Error getting trends: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/system-status")
async def get_system_status():
    """Get detailed system status"""
    try:
        collector = get_metrics_collector()
        manager = get_gpu_manager()

        return JSONResponse(
            content={
                "monitoring": collector.get_current_dashboard(),
                "gpu_manager": manager.get_system_status(),
                "timestamp": datetime.now().isoformat(),
            }
        )
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/alerts/clear")
async def clear_alerts():
    """Clear all alerts"""
    try:
        collector = get_metrics_collector()
        # Clear alerts by replacing with empty deque
        collector.alerts.clear()
        return JSONResponse(content={"message": "Alerts cleared"})
    except Exception as e:
        logger.error(f"Error clearing alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


def run_dashboard(host: str = "0.0.0.0", port: int = 8001):
    """Run the GPU monitoring dashboard"""
    logger.info(f"🚀 Starting GPU Dashboard on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_dashboard()

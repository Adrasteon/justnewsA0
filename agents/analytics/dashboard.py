"""
Advanced Analytics Dashboard for JustNews

Provides comprehensive web-based analytics interface with:
- Real-time performance monitoring
- Historical trend analysis
- Agent performance profiling
- System health monitoring
- Bottleneck detection and recommendations
- Interactive charts and visualizations
"""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agents.analytics.analytics_engine import get_analytics_engine

# Get the analytics engine instance
analytics_engine = get_analytics_engine()

# FastAPI app for analytics dashboard
analytics_app = FastAPI(title="JustNews Advanced Analytics Dashboard")

# Templates and static files
templates_dir = Path(__file__).parent / "analytics" / "templates"
static_dir = Path(__file__).parent / "analytics" / "static"

templates_dir.mkdir(parents=True, exist_ok=True)
static_dir.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(templates_dir))

# Mount static files
analytics_app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@analytics_app.get("/", response_class=HTMLResponse)
async def analytics_dashboard(request: Request):
    """Main analytics dashboard page"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@analytics_app.get("/health")
async def health_check():
    """Health endpoint for analytics dashboard service."""
    try:
        health = analytics_engine.get_system_health()
        return JSONResponse(
            content={
                "service": "analytics-dashboard",
                "status": "healthy",
                "health": health,
            }
        )
    except Exception as e:
        return JSONResponse(
            content={
                "service": "analytics-dashboard",
                "status": "degraded",
                "error": str(e),
            },
            status_code=503,
        )


@analytics_app.get("/api/health")
async def get_system_health():
    """Get system health metrics"""
    try:
        health = analytics_engine.get_system_health()
        return JSONResponse(content=health)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Health check failed: {str(e)}"
        ) from e


@analytics_app.get("/api/realtime/{hours}")
async def get_realtime_analytics(hours: int = 1):
    """Get real-time analytics for specified hours"""
    try:
        if hours < 1 or hours > 24:
            raise HTTPException(
                status_code=400, detail="Hours must be between 1 and 24"
            )

        analytics = analytics_engine.get_performance_metrics(hours=hours)
        return JSONResponse(content=analytics)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Analytics retrieval failed: {str(e)}"
        ) from e


@analytics_app.get("/api/agent/{agent_name}/{hours}")
async def get_agent_profile(agent_name: str, hours: int = 24):
    """Get performance profile for specific agent"""
    try:
        if hours < 1 or hours > 168:  # Max 1 week
            raise HTTPException(
                status_code=400, detail="Hours must be between 1 and 168"
            )

        profile = analytics_engine.get_agent_profile(agent_name, hours=hours)
        return JSONResponse(content=profile)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Agent profile retrieval failed: {str(e)}"
        ) from e


@analytics_app.get("/api/trends/{hours}")
async def get_performance_trends(hours: int = 24):
    """Get performance trends analysis"""
    try:
        analytics = analytics_engine.get_performance_metrics(hours=hours)

        # Extract trends, bottlenecks, and recommendations from analytics data
        trends = analytics.get("performance_trends", {})
        bottlenecks = analytics.get("bottleneck_indicators", [])
        recommendations = analytics.get("optimization_recommendations", [])

        return JSONResponse(
            content={
                "trends": trends,
                "bottlenecks": bottlenecks,
                "recommendations": recommendations,
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Trends analysis failed: {str(e)}"
        ) from e


@analytics_app.get("/api/report/{hours}")
async def get_analytics_report(hours: int = 24):
    """Get comprehensive analytics report"""
    try:
        report = analytics_engine.export_analytics_report(hours=hours)
        return JSONResponse(content=report)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Report generation failed: {str(e)}"
        ) from e


@analytics_app.get("/api/optimization-recommendations")
async def get_optimization_recommendations(hours: int = 24):
    """Get advanced optimization recommendations"""
    try:
        recommendations = analytics_engine.get_optimization_recommendations(hours)
        return JSONResponse(content=recommendations)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Optimization analysis failed: {str(e)}"
        ) from e


@analytics_app.get("/api/optimization-insights")
async def get_optimization_insights():
    """Get optimization insights and analytics"""
    try:
        # This functionality might be part of the optimization recommendations
        # For now, return a subset of recommendations as insights
        recommendations = analytics_engine.get_optimization_recommendations(hours=24)

        # Group recommendations by category for insights
        insights = {
            "total_recommendations": len(recommendations),
            "categories": {},
            "priorities": {},
            "high_impact": [r for r in recommendations if r.get("impact_score", 0) > 7],
            "quick_wins": [
                r for r in recommendations if r.get("complexity", "high") == "low"
            ],
        }

        # Count by category and priority
        for rec in recommendations:
            category = rec.get("category", "unknown")
            priority = rec.get("priority", "unknown")

            insights["categories"][category] = (
                insights["categories"].get(category, 0) + 1
            )
            insights["priorities"][priority] = (
                insights["priorities"].get(priority, 0) + 1
            )

        return JSONResponse(content=insights)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Insights generation failed: {str(e)}"
        ) from e


@analytics_app.post("/api/record-metric")
async def record_custom_metric(metric_data: dict[str, Any]):
    """Record a custom performance metric"""
    try:
        # Validate required fields
        required_fields = [
            "agent_name",
            "operation",
            "processing_time_s",
            "batch_size",
            "success",
        ]
        for field in required_fields:
            if field not in metric_data:
                raise HTTPException(
                    status_code=400, detail=f"Missing required field: {field}"
                )

        # Record the metric using the engine
        success = analytics_engine.record_performance_metric(metric_data)

        if success:
            return JSONResponse(
                content={"status": "success", "message": "Metric recorded successfully"}
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to record metric")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Metric recording failed: {str(e)}"
        ) from e


@analytics_app.get("/api/service-info")
async def get_service_info():
    """Get analytics service information and capabilities"""
    try:
        info = analytics_engine.get_service_info()
        return JSONResponse(content=info)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Service info retrieval failed: {str(e)}"
        ) from e


@analytics_app.get("/api/engine-health")
async def get_engine_health():
    """Get detailed engine health information"""
    try:
        health_info = await analytics_engine.health_check()
        return JSONResponse(content=health_info)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Engine health check failed: {str(e)}"
        ) from e


def create_analytics_app() -> FastAPI:
    """Create and return the analytics dashboard FastAPI app"""
    return analytics_app


def start_analytics_dashboard(host: str = "0.0.0.0", port: int = 8012):
    """Start the analytics dashboard server (standalone mode)"""
    import uvicorn

    uvicorn.run(analytics_app, host=host, port=port)


if __name__ == "__main__":
    start_analytics_dashboard()

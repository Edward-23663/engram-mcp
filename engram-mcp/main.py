from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging

from app.core.config import get_settings
from app.models.memory import init_db
from app.core.redis import redis_client
from app.core.rabbitmq import rabbitmq_client
from app.api.routes import router
from app.mcp.adapter import mcp_adapter, MCPRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Engram MCP...")
    
    # Initialize database
    await init_db()
    logger.info("Database initialized")
    
    # Connect to Redis
    try:
        await redis_client.connect()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
    
    # Connect to RabbitMQ
    try:
        await rabbitmq_client.connect()
        logger.info("RabbitMQ connected")
    except Exception as e:
        logger.warning(f"RabbitMQ connection failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Engram MCP...")
    await redis_client.close()
    await rabbitmq_client.close()


app = FastAPI(
    title="Engram MCP",
    description="Context-Aware Automatic Memory System",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "engram-mcp"}


# Include API routes
app.include_router(router)


# MCP endpoint
@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP protocol endpoint"""
    try:
        body = await request.json()
        mcp_request = MCPRequest(**body)
        response = await mcp_adapter.handle_request(mcp_request)
        return response.model_dump()
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# Alternative MCP endpoint (JSON-RPC style)
@app.post("/mcp/rpc")
async def mcp_rpc_endpoint(request: Request):
    """MCP JSON-RPC style endpoint"""
    try:
        body = await request.json()
        
        # Handle JSON-RPC format
        method = body.get("method")
        params = body.get("params", {})
        
        mcp_request = MCPRequest(
            method=method,
            params=params,
            namespace=params.get("namespace", "default")
        )
        
        response = await mcp_adapter.handle_request(mcp_request)
        
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": response.model_dump() if response.success else None,
            "error": {"message": response.error} if not response.success else None,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "error": {"message": str(e)}
            }
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
    )

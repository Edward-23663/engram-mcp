#!/usr/bin/env python3
"""
Engram MCP Auto-Healer Script
Automatically tests, runs, and repairs MCP service on opencode startup
"""
import os
import sys
import json
import time
import subprocess
import threading
import signal
import atexit
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/engram_mcp_healer.log'),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger('mcp-auto-healer')

# Configuration
CONFIG = {
    'mcp_script': os.path.join(os.path.dirname(__file__), 'mcp_direct.py'),
    'health_check_port': 18084,
    'max_retries': 3,
    'retry_delay': 2,
    'test_timeout': 10,
    'max_startup_time': 30,
    'check_interval': 60,  # Health check interval in seconds
}

# Global state
mcp_process = None
health_check_thread = None
stop_event = threading.Event()

def setup_environment():
    """Setup environment variables for MCP"""
    env = os.environ.copy()
    env.update({
        'DATABASE_URL': env.get('DATABASE_URL', 'postgresql+asyncpg://app:postgres_password@localhost:5432/appdb'),
        'REDIS_URL': env.get('REDIS_URL', 'redis://:redis_password@localhost:6379/0'),
        'RABBITMQ_URL': env.get('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/'),
        'LITELLM_BASE_URL': env.get('LITELLM_BASE_URL', 'http://localhost:4000'),
        'LITELLM_API_KEY': env.get('LITELLM_API_KEY', 'litellm_key_123'),
        'LITELLM_EMBED_MODEL': env.get('LITELLM_EMBED_MODEL', 'text-embedding-3-small'),
        'LITELLM_CHAT_MODEL': env.get('LITELLM_CHAT_MODEL', 'gpt-4o-mini'),
        'NAMESPACE': env.get('NAMESPACE', 'default'),
    })
    return env

def check_database():
    """Check if database is accessible"""
    try:
        result = subprocess.run(
            ['docker', 'exec', 'postgres', 'psql', '-U', 'app', '-d', 'appdb', '-c', 'SELECT 1;'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        logger.warning(f"Database check failed: {e}")
        return False

def check_redis():
    """Check if Redis is accessible"""
    try:
        result = subprocess.run(
            ['docker', 'exec', 'redis', 'redis-cli', 'ping'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0 and 'PONG' in result.stdout
    except Exception as e:
        logger.warning(f"Redis check failed: {e}")
        return False

def test_mcp_server():
    """Test MCP server functionality"""
    logger.info("Testing MCP server...")
    try:
        result = subprocess.run(
            ['python3', CONFIG['mcp_script']],
            input=json.dumps({
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            }),
            capture_output=True,
            text=True,
            timeout=CONFIG['test_timeout'],
            env=setup_environment()
        )
        
        if result.returncode == 0:
            try:
                response = json.loads(result.stdout)
                if "result" in response and "tools" in response["result"]:
                    tool_count = len(response["result"]["tools"])
                    logger.info(f"MCP server test passed: {tool_count} tools available")
                    return True, tool_count
            except json.JSONDecodeError:
                logger.error(f"MCP server returned invalid JSON: {result.stdout[:100]}")
        else:
            logger.error(f"MCP server test failed: {result.stderr}")
        
        return False, 0
    except subprocess.TimeoutExpired:
        logger.error("MCP server test timeout")
        return False, 0
    except Exception as e:
        logger.error(f"MCP server test error: {e}")
        return False, 0

def start_mcp_server():
    """Start MCP server in background"""
    global mcp_process
    
    if mcp_process and mcp_process.poll() is None:
        logger.info("MCP server already running")
        return True
    
    logger.info("Starting MCP server...")
    try:
        mcp_process = subprocess.Popen(
            ['python3', CONFIG['mcp_script']],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=setup_environment(),
            bufsize=1,
            universal_newlines=True
        )
        
        # Give it a moment to start
        time.sleep(1)
        
        if mcp_process.poll() is not None:
            stderr_output = mcp_process.stderr.read() if mcp_process.stderr else "No stderr"
            logger.error(f"MCP server failed to start: {stderr_output}")
            return False
        
        logger.info("MCP server started successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")
        return False

def stop_mcp_server():
    """Stop MCP server gracefully"""
    global mcp_process
    
    if mcp_process and mcp_process.poll() is None:
        logger.info("Stopping MCP server...")
        try:
            mcp_process.terminate()
            mcp_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("MCP server did not terminate gracefully, forcing...")
            mcp_process.kill()
        except Exception as e:
            logger.error(f"Error stopping MCP server: {e}")
        
        mcp_process = None
        logger.info("MCP server stopped")

def repair_mcp_service():
    """Attempt to repair MCP service issues"""
    logger.info("Attempting to repair MCP service...")
    
    repairs = []
    
    # 1. Check and restart Docker services if needed
    docker_services = ['postgres', 'redis', 'rabbitmq']
    for service in docker_services:
        try:
            result = subprocess.run(
                ['docker', 'ps', '-f', f'name={service}', '--format', '{{.Status}}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0 or 'Up' not in result.stdout:
                logger.warning(f"Docker service {service} is not running, attempting to start...")
                subprocess.run(['docker', 'start', service], timeout=10)
                repairs.append(f"Started Docker service: {service}")
        except Exception as e:
            logger.error(f"Failed to check/start Docker service {service}: {e}")
    
    # 2. Ensure database tables exist
    try:
        subprocess.run(
            ['docker', 'exec', 'postgres', 'psql', '-U', 'app', '-d', 'appdb', '-c', 'SELECT 1 FROM memories LIMIT 1;'],
            capture_output=True,
            timeout=5
        )
    except:
        logger.warning("Database tables may not exist, attempting to initialize...")
        # This would require running the database initialization
        repairs.append("Checked database tables")
    
    # 3. Test MCP server after repairs
    success, tool_count = test_mcp_server()
    if success:
        repairs.append(f"MCP server repaired: {tool_count} tools available")
        return True, repairs
    else:
        repairs.append("MCP server repair failed")
        return False, repairs

def health_check_worker():
    """Background worker to periodically check MCP health"""
    logger.info("Starting health check worker...")
    
    check_count = 0
    while not stop_event.is_set():
        try:
            check_count += 1
            logger.debug(f"Health check #{check_count}")
            
            # Test MCP server
            success, tool_count = test_mcp_server()
            
            if not success:
                logger.warning("MCP server health check failed, attempting repair...")
                repair_success, repairs = repair_mcp_service()
                
                if repair_success:
                    logger.info(f"Repair successful: {', '.join(repairs)}")
                else:
                    logger.error("Repair failed, restarting MCP server...")
                    stop_mcp_server()
                    start_mcp_server()
            
            # Wait for next check
            stop_event.wait(CONFIG['check_interval'])
            
        except Exception as e:
            logger.error(f"Health check worker error: {e}")
            time.sleep(10)
    
    logger.info("Health check worker stopped")

def start_health_monitor():
    """Start health monitoring in background thread"""
    global health_check_thread
    
    if health_check_thread and health_check_thread.is_alive():
        logger.info("Health monitor already running")
        return
    
    stop_event.clear()
    health_check_thread = threading.Thread(target=health_check_worker, daemon=True)
    health_check_thread.start()
    logger.info("Health monitor started")

def stop_health_monitor():
    """Stop health monitoring"""
    logger.info("Stopping health monitor...")
    stop_event.set()
    
    if health_check_thread and health_check_thread.is_alive():
        health_check_thread.join(timeout=5)
        logger.info("Health monitor stopped")

def signal_handler(signum, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    cleanup()
    sys.exit(0)

def cleanup():
    """Cleanup resources"""
    logger.info("Cleaning up...")
    stop_health_monitor()
    stop_mcp_server()
    logger.info("Cleanup complete")

def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("Engram MCP Auto-Healer Starting")
    logger.info("=" * 60)
    
    # Register cleanup handlers
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Step 1: Check dependencies
    logger.info("Step 1: Checking dependencies...")
    deps_ok = True
    
    if not check_database():
        logger.error("Database check failed")
        deps_ok = False
    
    if not check_redis():
        logger.warning("Redis check failed (may not be critical)")
    
    if not deps_ok:
        logger.warning("Some dependencies failed, attempting to continue...")
    
    # Step 2: Test MCP server
    logger.info("Step 2: Testing MCP server...")
    success, tool_count = test_mcp_server()
    
    if not success:
        logger.warning("MCP server test failed, attempting repair...")
        repair_success, repairs = repair_mcp_service()
        
        if repair_success:
            logger.info(f"Repair successful: {', '.join(repairs)}")
            success = True
        else:
            logger.error("Repair failed")
    
    # Step 3: Start MCP server if needed
    if success:
        logger.info("Step 3: Ensuring MCP server is running...")
        if not start_mcp_server():
            logger.error("Failed to start MCP server")
            return 1
    
    # Step 4: Start health monitoring
    logger.info("Step 4: Starting health monitoring...")
    start_health_monitor()
    
    # Step 5: Report status
    logger.info("=" * 60)
    logger.info("Engram MCP Auto-Healer Status Report")
    logger.info("=" * 60)
    logger.info(f"Database: {'OK' if check_database() else 'FAILED'}")
    logger.info(f"Redis: {'OK' if check_redis() else 'FAILED'}")
    logger.info(f"MCP Server: {'RUNNING' if success else 'FAILED'}")
    logger.info(f"Tools Available: {tool_count if success else 0}")
    logger.info(f"Health Monitor: {'ACTIVE' if health_check_thread and health_check_thread.is_alive() else 'INACTIVE'}")
    logger.info("=" * 60)
    logger.info("Auto-healer is now monitoring MCP service")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
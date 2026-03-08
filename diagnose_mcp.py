#!/usr/bin/env python3
"""
Diagnose MCP loading issues for opencode
"""
import os
import sys
import json
import subprocess
import time

def check_mcp_server():
    """Check if MCP server works directly"""
    print("🔍 Testing MCP server directly...")
    try:
        result = subprocess.run(
            ['python3', 'engram-mcp/mcp_direct.py'],
            input=json.dumps({
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            }),
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.dirname(__file__)
        )
        
        if result.returncode == 0:
            response = json.loads(result.stdout)
            if "result" in response and "tools" in response["result"]:
                print(f"✅ MCP server works: {len(response['result']['tools'])} tools available")
                return True
            else:
                print(f"❌ MCP server returned unexpected format: {result.stdout[:200]}")
                return False
        else:
            print(f"❌ MCP server failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ MCP server check error: {e}")
        return False

def check_database():
    """Check database connection and data"""
    print("🔍 Checking database...")
    try:
        result = subprocess.run(
            ['docker', 'exec', 'postgres', 'psql', '-U', 'app', '-d', 'appdb', '-c', 'SELECT COUNT(*) FROM memories;'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                count = lines[-2].strip()
                print(f"✅ Database has {count} memories")
                return True
        print(f"❌ Database check failed: {result.stderr}")
        return False
    except Exception as e:
        print(f"❌ Database check error: {e}")
        return False

def check_opencode_config():
    """Check opencode.json configuration"""
    print("🔍 Checking opencode.json...")
    config_path = os.path.join(os.path.dirname(__file__), 'opencode.json')
    if not os.path.exists(config_path):
        print(f"❌ opencode.json not found at {config_path}")
        return False
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        if "mcp" in config and "engram-memory" in config["mcp"]:
            mcp_config = config["mcp"]["engram-memory"]
            print(f"✅ opencode.json has engram-memory MCP config")
            print(f"   Command: {mcp_config.get('command')}")
            print(f"   Enabled: {mcp_config.get('enabled', False)}")
            return True
        else:
            print("❌ opencode.json missing engram-memory MCP config")
            return False
    except Exception as e:
        print(f"❌ Error reading opencode.json: {e}")
        return False

def check_mcp_process():
    """Check if MCP process is running"""
    print("🔍 Checking MCP processes...")
    try:
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True
        )
        
        mcp_processes = []
        for line in result.stdout.split('\n'):
            if 'mcp_' in line.lower() and 'python' in line:
                mcp_processes.append(line.strip())
        
        if mcp_processes:
            print(f"✅ Found {len(mcp_processes)} MCP processes:")
            for proc in mcp_processes[:3]:  # Show first 3
                print(f"   {proc[:100]}...")
            return True
        else:
            print("❌ No MCP processes found")
            return False
    except Exception as e:
        print(f"❌ Process check error: {e}")
        return False

def main():
    print("=" * 60)
    print("Engram MCP Diagnostic Tool")
    print("=" * 60)
    
    checks = [
        ("opencode.json config", check_opencode_config),
        ("MCP server direct", check_mcp_server),
        ("Database connection", check_database),
        ("MCP processes", check_mcp_process),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n{name}:")
        try:
            success = check_func()
            results.append((name, success))
        except Exception as e:
            print(f"   ❌ Check failed with exception: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("Diagnostic Summary:")
    print("=" * 60)
    
    all_passed = True
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
        if not success:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All checks passed! MCP should be working.")
        print("\nIf opencode still doesn't show MCP tools, try:")
        print("1. Restart opencode session")
        print("2. Check opencode logs for MCP loading errors")
        print("3. Verify opencode has permission to execute MCP scripts")
    else:
        print("❌ Some checks failed. Issues detected:")
        print("\nRecommended actions:")
        print("1. Fix the failed checks above")
        print("2. Restart opencode session")
        print("3. Check Docker container logs: docker logs engram-mcp")
        print("4. Verify environment variables are correct")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
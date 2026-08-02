# PLM-IQ MCP Server Setup Guide

This guide explains how to connect PLM-IQ's MCP Server to popular LLM clients like Claude Desktop, Cursor, and VS Code.

## What is MCP?

The **Model Context Protocol (MCP)** allows LLM clients (like Claude Desktop) to connect to external tools and data sources. PLM-IQ's MCP Server exposes all PLM tools (search parts, get BOM, etc.) to MCP-compatible clients.

## How it Works

The MCP server is a **separate process** from the PLM-IQ web app. It:
- Connects directly to the PLM-IQ database (same database as the web app)
- Shares the same tool implementations (`app/plmassistant/plm_tools.py`)
- Runs independently - you don't need to start the web app to use the MCP server

This means you can use both the web app assistant and the MCP server simultaneously - they share the same data but operate independently.

## Prerequisites

1. **PLM-IQ database exists** (run the app once to initialize it)
2. **`.env` file configured** in the PLM-IQ root directory
3. **Python environment** with MCP SDK installed:
   ```bash
   pip install mcp
   ```
4. **LLM Client** installed (Claude Desktop, Cursor, etc.)

---

## 1. Claude Desktop

### Windows

1. Open Claude Desktop
2. Go to **Settings** → **Developer** → **Edit Config**
   - Config file location: `%APPDATA%\Claude\claude_desktop_config.json`
   - Or manually edit: `C:\Users\YourUsername\AppData\Roaming\Claude\claude_desktop_config.json`

3. Add PLM-IQ MCP server:
   ```json
   {
     "mcpServers": {
       "plm-iq": {
         "command": "python",
         "args": ["C:\\ramesh2026\\work\\plm-iq\\plm_mcp\\server.py"]
       }
     }
   }
   ```

4. **Restart Claude Desktop**

5. **Verify**: Look for "plm-iq" in the tools menu (hammer icon) or type `/tools` in Claude

### Mac/Linux

1. Open Claude Desktop config:
   ```bash
   # Mac
   nano ~/Library/Application\ Support/Claude/claude_desktop_config.json

   # Linux
   nano ~/.config/Claude/claude_desktop_config.json
   ```

2. Add the same config (use forward slashes for paths):
   ```json
   {
     "mcpServers": {
       "plm-iq": {
         "command": "python",
         "args": ["/path/to/plm-iq/plm_mcp/server.py"]
       }
     }
   }
   ```

3. Restart Claude Desktop

---

## 2. Cursor

Cursor has built-in MCP support.

1. Open Cursor
2. Go to **Settings** → **Features** → **MCP**
3. Click **+ Add new MCP server**
4. Fill in:
   - **Name**: `plm-iq`
   - **Type**: `stdio`
   - **Command**: `python C:\ramesh2026\work\plm-iq\plm_mcp/server.py`

5. Save and restart Cursor

---

## 3. VS Code (with MCP Extension)

### Option A: Using MCP Extension

1. Install the **MCP Extension** in VS Code
2. Open VS Code settings (`Ctrl+,` or `Cmd+,`)
3. Search for "MCP" and add server config:
   ```json
   {
     "mcp.servers": {
       "plm-iq": {
         "command": "python",
         "args": ["C:\\ramesh2026\\work\\plm-iq\\plm_mcp/server.py"]
       }
     }
   }
   ```

### Option B: Using Copilot with MCP

If using GitHub Copilot with MCP support:

1. Create `.vscode/mcp.json` in your workspace:
   ```json
   {
     "servers": {
       "plm-iq": {
         "command": "python",
         "args": ["${workspaceFolder}/plm_mcp/server.py"]
       }
     }
   }
   ```

2. Reload VS Code window

---

## 4. Testing with MCP Inspector

The MCP Inspector is a debugging tool for MCP servers.

### Install and Run

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Run inspector with your server
npx @modelcontextprotocol/inspector python plm_mcp/server.py
```

This opens a web UI where you can:
- See all registered tools
- Test tool calls
- View server logs

---

## 5. Available Tools

Once connected, these tools are available:

| Tool | Description |
|------|-------------|
| `list_parts` | List parts with filters (limit, status, sort) |
| `get_part` | Get full details for a part |
| `search_parts` | Search parts by query |
| `create_part` | Create a new part from template |
| `update_part_status` | Update part status |
| `get_bom` | Get Bill of Materials |
| `get_costing` | Get costing details |
| `get_eco` | Get Engineering Change Order |
| `search_ecos` | Search ECOs |
| `get_aml` | Get Approved Manufacturer List |
| `get_avl` | Get Approved Vendor List |
| `get_cad` | Get CAD file metadata |

---

## 6. Example Usage in Claude Desktop

Once connected, you can ask Claude:

```
User: "List the latest 5 parts in PLM"
Claude: [calls list_parts tool with limit=5, sort="modified_date"]
       → Returns the 5 most recently updated parts

User: "Get details for part BB-001"
Claude: [calls get_part tool]
       → Returns full part details

User: "What is the BOM for FRM-003?"
Claude: [calls get_bom tool]
       → Returns the Bill of Materials
```

---

## 7. Troubleshooting

### MCP Server Won't Start

**Check Python path**:
```bash
# Test the server manually
python C:\ramesh2026\work\plm-iq\plm_mcp/server.py
```

**Check .env file**: Ensure `.env` exists in PLM-IQ root with valid config.

**Check dependencies**:
```bash
pip install mcp python-dotenv
```

### Tools Don't Appear in Claude

1. **Restart Claude Desktop** (required after config change)
2. **Check config syntax**: Ensure `claude_desktop_config.json` is valid JSON
3. **Check logs**:
   - Windows: `%APPDATA%\Claude\logs\`
   - Mac: `~/Library/Logs/Claude/`

### Tool Execution Fails

**Check database connection**: Ensure PLM-IQ database is accessible.

**Check tool arguments**: MCP clients may pass arguments differently. Check server logs:
```bash
# Run server manually to see logs
python plm_mcp/server.py
```

---

## 8. Advanced Configuration

### Custom Python Environment

If using a virtual environment:

```json
{
  "mcpServers": {
    "plm-iq": {
      "command": "C:\\path\\to\\venv\\Scripts\\python.exe",
      "args": ["C:\\ramesh2026\\work\\plm-iq\\plm_mcp/server.py"]
    }
  }
}
```

### Environment Variables

The MCP server reads from `.env` in the PLM-IQ root. Ensure these are set:
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `DATABASE_URL` (if using SQLite, ensure path is correct)

---

## 9. Security Notes

- The MCP server runs locally and accesses your PLM database directly
- Only expose the MCP server to trusted LLM clients
- Consider adding authentication if exposing over network (HTTP mode)

---

## 10. Next Steps

1. **Test the connection** with MCP Inspector
2. **Try example queries** in Claude Desktop
3. **Customize tools** by editing `plm_mcp/server.py`
4. **Add more tools** from `app/plmassistant/plm_tools.py`

For more info on MCP: https://modelcontextprotocol.io

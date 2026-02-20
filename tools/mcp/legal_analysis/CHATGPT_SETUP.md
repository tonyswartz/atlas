# ChatGPT Desktop Setup Guide

This guide shows how to connect the Legal Analysis MCP server to ChatGPT Desktop via HTTPS.

## Architecture

- **Local HTTP Server**: Runs on `localhost:8000` (managed by launchd)
- **Cloudflare Tunnel**: Exposes as `https://legal.tswartz.com`
- **ChatGPT Desktop**: Connects to HTTPS endpoint

## Prerequisites

### 1. DNS Configuration

Add DNS record in Cloudflare dashboard:

1. Log in to Cloudflare
2. Select domain: `tswartz.com`
3. Go to DNS → Records
4. Add CNAME record:
   - **Name**: `legal`
   - **Target**: `bca2fb86-d027-498d-9f60-a341957a0dfa.cfargotunnel.com`
   - **Proxy status**: Proxied (orange cloud ☁️)

### 2. Add Security (Recommended)

**IMPORTANT:** The HTTPS endpoint will be publicly accessible without auth.

See **[SECURITY_SETUP.md](SECURITY_SETUP.md)** for setting up Cloudflare Access authentication. This is **highly recommended** before exposing the endpoint.

Quick setup:
1. Cloudflare Dashboard → Zero Trust → Access → Applications
2. Create application for `legal.tswartz.com`
3. Add policy: Allow specific emails only
4. ChatGPT will authenticate via browser or service token

### 3. Restart Cloudflare Tunnel

The tunnel config has been updated automatically. Restart it:

```bash
# Find the cloudflared process
pgrep -fl cloudflared

# Restart it (replace PID with actual process ID)
sudo brew services restart cloudflared
```

Or manually:
```bash
cloudflared tunnel restart
```

### 3. Verify HTTP Server is Running

```bash
curl http://localhost:8000/sse
```

Should connect (may hang - that's normal for SSE endpoint).

## ChatGPT Desktop Configuration

### Step 1: Enable Developer Mode

1. Open ChatGPT Desktop
2. Go to **Settings** → **Apps** → **Advanced settings**
3. Enable **Developer mode**

**Note**: Developer mode requires Pro, Plus, Business, Enterprise, or Edu account.

### Step 2: Create MCP Connector

1. In Settings, click **Connectors** → **Create**
2. Fill in connector details:

   - **Name**: `Legal Analysis`
   - **Endpoint URL**: `https://legal.tswartz.com/sse`
   - **Transport**: Server-Sent Events (SSE)
   - **Authentication**: None

3. Click **Create**

### Step 3: Enable in Conversation

1. Start a new ChatGPT conversation
2. Click the **Plus menu** (⊕)
3. Select **Developer mode**
4. Select the **Legal Analysis** app
5. Tools should now be available

## Available Tools

Once connected, ChatGPT can access:

1. **list_case_files** - List all PDFs in drop folder
2. **analyze_dui_criminal** - WA DUI criminal defense analysis
3. **analyze_dui_dol_hearing** - DOL license suspension hearing analysis
4. **analyze_criminal_case** - General criminal case analysis

## Testing

1. Drop a PDF in: `~/Library/CloudStorage/Dropbox/MCP Analysis/`

2. In ChatGPT, say:
   ```
   List case files
   ```

3. Analyze a file:
   ```
   Analyze "filename.pdf" for DUI criminal issues
   ```

## Privacy & Security

✅ **What Happens:**
1. PDF stays on your Mac
2. Server extracts text locally (with OCR if scanned)
3. Server sanitizes ALL PII locally
4. Only sanitized text sent to ChatGPT via HTTPS
5. Sanitization map saved locally only

✅ **What's Redacted:**
- Names → `[PERSON_1]`, `[PERSON_2]`
- Case numbers → `[CASE_NUM_001]`
- Addresses → `[ADDRESS_001]`
- License plates → `[PLATE_001]`
- SSN → `[SSN_REDACTED]`
- DOB → `[REDACTED]`
- Phone numbers → `[PHONE_REDACTED]`

✅ **What's Preserved:**
- BAC results
- Test times/dates
- Legal citations
- Case law
- Factual observations

⚠️ **Consider:**
- Conversation history stored on OpenAI servers (sanitized)
- Fact patterns may still be identifiable
- Use professional judgment
- Check your bar's ethics rules

## Troubleshooting

### "Connection failed"

```bash
# Check DNS
dig legal.tswartz.com

# Check tunnel
pgrep -fl cloudflared

# Check HTTP server
curl http://localhost:8000/sse

# Check launchd service
launchctl list | grep legal-mcp-http
```

### "No tools showing"

- Verify Developer mode is enabled
- Check connector is active in conversation
- Try removing and re-adding connector
- Restart ChatGPT Desktop completely

### "No files found"

- Check: `~/Library/CloudStorage/Dropbox/MCP Analysis/`
- Verify files are PDFs
- Check Dropbox sync completed

## Comparing Claude vs ChatGPT

You can use **BOTH** systems to compare legal analyses:

### Claude Desktop (Local, Faster)
- **Setup**: See `SETUP.md`
- **Config**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Transport**: stdio (direct Python execution)
- **Speed**: Faster (no network overhead)
- **Access**: Local machine only

### ChatGPT Desktop (HTTPS, Remote)
- **Setup**: This guide
- **Config**: Cloudflare Tunnel + Developer mode
- **Transport**: SSE over HTTPS
- **Speed**: Slightly slower (network roundtrip)
- **Access**: Can work from anywhere with tunnel

### Workflow for Comparison

1. Drop PDF in `~/Library/CloudStorage/Dropbox/MCP Analysis/`
2. Open Claude Desktop: "Analyze this for DUI issues"
3. Open ChatGPT Desktop: "Analyze this for DUI issues"
4. Compare the analyses side-by-side
5. Both use identical sanitization and source materials

## Service Management

### Start HTTP Server
```bash
launchctl load ~/Library/LaunchAgents/com.atlas.legal-mcp-http.plist
```

### Stop HTTP Server
```bash
launchctl unload ~/Library/LaunchAgents/com.atlas.legal-mcp-http.plist
```

### View Logs
```bash
tail -f ~/atlas/logs/legal-mcp-http.log
tail -f ~/atlas/logs/legal-mcp-http.error.log
```

### Check Status
```bash
launchctl list | grep legal-mcp-http
curl http://localhost:8000/
```

## Next Steps

1. ✅ HTTP server running on localhost:8000
2. ✅ Cloudflare config updated
3. ⏳ Add DNS record in Cloudflare dashboard
4. ⏳ Restart Cloudflare tunnel
5. ⏳ Enable Developer mode in ChatGPT
6. ⏳ Create connector in ChatGPT
7. ⏳ Test with a case file

See [SETUP.md](SETUP.md) for Claude Desktop setup.

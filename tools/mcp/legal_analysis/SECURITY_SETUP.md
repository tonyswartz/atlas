# Security Setup for Legal Analysis MCP

## Problem

The HTTPS endpoint (`https://legal.tswartz.com`) would be publicly accessible without authentication. Anyone who discovers the URL could potentially use your MCP server.

## Recommended Solution: Cloudflare Access

Use Cloudflare's Zero Trust platform to add authentication **in front** of the endpoint. This requires zero code changes to the MCP server.

### How It Works

1. User tries to access `https://legal.tswartz.com/sse`
2. Cloudflare intercepts and shows login page
3. User authenticates (email verification, Google, etc.)
4. Cloudflare allows access after successful auth
5. ChatGPT connector can authenticate and use tools

### Setup Steps

#### 1. Enable Cloudflare Access (Free)

1. Log in to Cloudflare Dashboard
2. Select your domain: `tswartz.com`
3. Go to **Zero Trust** in left sidebar
4. Click **Get started** (free plan available)
5. Choose a team name (e.g., `tswartz-team`)

#### 2. Create Access Application

1. In Zero Trust dashboard, go to **Access** → **Applications**
2. Click **Add an application**
3. Select **Self-hosted**
4. Configure:

   **Application Configuration:**
   - **Name**: `Legal Analysis MCP`
   - **Session Duration**: 24 hours
   - **Application domain**: `legal.tswartz.com`
   - **Path**: All paths (or specific: `/sse`)

   **Identity Providers:**
   - Enable **One-time PIN** (email verification)
   - Or add **Google** (recommended)
   - Or add **GitHub**

   **Policies:**
   - Create policy: `Legal Analysis Access`
   - **Action**: Allow
   - **Include**: Emails ending in `@yourdomain.com` (or specific emails)
   - Or: Include specific email addresses

5. Click **Save**

#### 3. Test Authentication

1. Open private/incognito browser window
2. Navigate to: `https://legal.tswartz.com`
3. Should see Cloudflare Access login page
4. Authenticate with your email/Google/GitHub
5. Should then reach the endpoint

#### 4. Configure ChatGPT Connector with Auth

When creating the ChatGPT connector, Cloudflare Access works transparently:

1. ChatGPT attempts to connect to `https://legal.tswartz.com/sse`
2. Cloudflare redirects to auth
3. You authenticate once in browser
4. Cloudflare sets cookie
5. ChatGPT connector uses same session

**Alternative: Service Token** (for non-browser clients)

If ChatGPT can't handle browser auth flow:

1. In Cloudflare Access, go to **Service Auth** → **Service Tokens**
2. Create a token for the Legal Analysis app
3. Copy Client ID and Client Secret
4. In ChatGPT connector settings, add headers:
   - `CF-Access-Client-Id`: [your client id]
   - `CF-Access-Client-Secret`: [your client secret]

## Alternative Solutions

### Option 2: API Key Authentication (Code Changes)

Add bearer token auth to the MCP server itself.

**Pros:**
- Simple, no third-party service
- Full control

**Cons:**
- Requires code changes
- Need to manage API keys
- Less sophisticated than OAuth

**Implementation:**

1. Generate API key:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Store in environment:
   ```bash
   # Add to .env
   MCP_API_KEY=your-generated-key
   ```

3. Update server code to check `Authorization: Bearer <token>` header

4. Configure ChatGPT connector with custom header

### Option 3: IP Whitelist

Restrict access to specific IP addresses in Cloudflare.

**Pros:**
- Very simple
- No authentication flow

**Cons:**
- Breaks when IP changes (home internet, mobile)
- Not portable
- Can't use from different locations

**Implementation:**

1. Cloudflare Dashboard → Legal Analysis Access application
2. Add policy rule: **IP ranges** include your IP
3. Block all others

### Option 4: Keep Private (No Public Tunnel)

Don't expose via Cloudflare Tunnel at all.

**Pros:**
- Maximum security
- No authentication needed

**Cons:**
- Can't use ChatGPT Desktop remotely
- Can only use Claude Desktop (local only)

**Implementation:**

1. Remove `legal.tswartz.com` from tunnel config
2. Only use Claude Desktop with local stdio transport
3. For remote access, use VPN/Tailscale

## Recommendation

**Use Cloudflare Access** because:

✅ No code changes
✅ Free for personal use
✅ Professional authentication (OAuth, email verification)
✅ Works from anywhere
✅ Can revoke access anytime
✅ Audit logs of who accessed when
✅ Same infrastructure you already use (Cloudflare)

**Fallback:** If ChatGPT connector can't handle Cloudflare Access auth flow, use Service Tokens (still zero code changes).

## Testing Security

After setup, verify:

```bash
# Should require authentication
curl https://legal.tswartz.com/sse
# → Cloudflare Access login page or 401

# After authenticating in browser, cookies should work
curl -H "Cookie: CF_Authorization=..." https://legal.tswartz.com/sse
# → Should connect
```

## Privacy Layers

With this setup, you have **defense in depth**:

1. **Cloudflare Access**: Authentication required to reach endpoint
2. **HTTPS**: Encrypted transport via Cloudflare Tunnel
3. **Local Sanitization**: PII stripped before leaving your machine
4. **Drop Folder**: PDFs never uploaded, processed locally only

## Audit & Monitoring

Cloudflare Access provides:
- **Access Logs**: See who authenticated and when
- **Session Management**: View active sessions, revoke anytime
- **Alerts**: Get notified of suspicious access patterns

Access via: Zero Trust Dashboard → Logs → Access

## Questions?

**Q: Does this slow down the MCP connection?**
A: First connection requires auth (1-2 seconds). Subsequent requests use cached session, no overhead.

**Q: Can I use different auth for Claude vs ChatGPT?**
A: Yes! Claude uses local stdio (no auth needed). ChatGPT uses HTTPS with Cloudflare Access.

**Q: What if I want multiple people to use it?**
A: Add their emails to the Access policy. They'll authenticate separately.

**Q: Can I disable auth temporarily for testing?**
A: Yes, disable the Access application in Cloudflare dashboard. Re-enable when done.

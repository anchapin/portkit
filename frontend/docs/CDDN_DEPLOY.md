# CDN Deployment Guide for Portkit Frontend

This document describes how to deploy the Portkit frontend SPA to various CDN platforms.

## Overview

The frontend is a Vite + React SPA configured for static deployment. All routing is handled client-side via React Router.

## Deployment Options

### 1. Vercel (Recommended)

1. Install Vercel CLI: `npm i -g vercel`
2. Run `vercel` in the `frontend/` directory
3. Set environment variables:
   - `VITE_API_URL`
   - `VITE_API_BASE_URL`
4. Deploy with `vercel --prod`

Or connect your GitHub repo to Vercel and it will auto-detect settings from `vercel.json`.

### 2. Cloudflare Pages

1. Go to [Cloudflare Pages](https://pages.cloudflare.com/)
2. Connect your GitHub repository
3. Configure:
   - **Build command**: `pnpm run build`
   - **Build output directory**: `dist`
   - **Root folder**: `frontend`
4. Add environment variables from `.env.example`
5. Deploy

The `public/_redirects` and `public/_headers` files handle routing and security headers. These are copied to `dist/` during build.

### 3. Tigris (Self-hosted S3-compatible)

```bash
# Build the frontend
cd frontend && pnpm install && pnpm run build

# Upload to Tigris
tigris upload --dir dist/ <bucket-name>

# Configure CDN headers via Tigris dashboard or CLI
tigris cdn headers set --path "/*" --header "Cache-Control:no-cache"
tigris cdn headers set --path "/assets/*" --header "Cache-Control:public,max-age=31536000,immutable"
```

## Build Output

The `dist/` directory contains:
- `index.html` - Main HTML entry point
- `assets/` - Chunked JS/CSS bundles with content hashing
- `_redirects` - Netlify/Cloudflare Pages SPA routing fallback
- `_headers` - Security and cache headers for Cloudflare Pages

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_API_URL` | Backend API URL | `https://api.portkit.dev` |
| `VITE_API_BASE_URL` | Base URL for API | `https://api.portkit.dev` |
| `VITE_WS_URL` | WebSocket URL | `wss://api.portkit.dev` |

## SPA Routing

All non-asset routes are rewrites to `/index.html` to support client-side React Router navigation. This is handled by:
- `dist/_redirects` - for Netlify/Cloudflare Pages
- `vercel.json` rewrites - for Vercel
- `nginx.conf` try_files directive - for Fly.io/Docker
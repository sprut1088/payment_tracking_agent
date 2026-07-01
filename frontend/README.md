# Frontend — ACH Payment Tracking Agent

React + TypeScript + Vite demo UI for the ACH Payment Tracking Agent.

At this bootstrap stage the app only renders a landing page that pings the
backend `/health` endpoint. Batch, customer, payment-detail, and demo-simulator
views are added in later prompts.

## Requirements

- Node.js 20+

## Install

```powershell
cd frontend
npm install
```

## Run

```powershell
npm run dev
```

The app is served at http://localhost:5173. Requests to `/health` and `/api`
are proxied to the backend at http://localhost:8000 (see `vite.config.ts`).

## Build

```powershell
npm run build
npm run preview
```

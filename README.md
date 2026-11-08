# Kitchen Copilot

AI-assisted Kitchen and Mess Management System for
Zaitoon International Girls Campus, Payyanur.

## Project Status

Initial development — Week 1.

## Objectives

- Purchase and supplier management
- Inventory and stock management
- Meal planning and quantity calculation
- Food preparation and distribution
- Outsourced food management
- Dashboard and reports
- AI-powered operational assistance

## Proposed Technology

- Frontend: Next.js + TypeScript
- Backend: FastAPI
- Action Executor: Flask
- Database: PostgreSQL + pgvector
- Agent Trace Storage: MongoDB
- Cache and Message Broker: Redis
- Background Tasks: Celery
- Reverse Proxy: Nginx
- Deployment: Docker and AWS

## Project Structure

- apps/web: Frontend
- services/api: Main backend API
- services/actions: Approved action executor
- infra: Infrastructure configuration
- docs: Project documentation
- spikes: Technical experiments
- scripts: Development and seed scripts

## Development Status

Week 1 foundation implemented: frontend, backend, authentication, role-based permissions, database migrations, Docker services, AI experiments and automated tests. Production AI integration and full action execution are not yet implemented.

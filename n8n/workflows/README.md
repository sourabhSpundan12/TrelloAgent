# n8n Workflow Definitions

This directory stores exported workflow definitions for the Agentic Task Manager.

## Purpose

- **Scheduled Reporting Triggers**: Periodic triggers (daily at 09:00, weekly on Mondays) notifying the reporting engine to calculate and persist employee workload snapshots.
- **Trello Webhook Sync**: Relaying Trello card move/edit events back to the backend `/api/v1/integrations/trello/webhook` endpoint.
- **External Notifications**: Relaying approval alerts and status digests to Slack/Discord/Email.


import { RegisteredTool } from '../types';

export const MOCK_TOOLS: RegisteredTool[] = [
  {
    id: 'TOOL-001',
    name: 'trello_create_card',
    description: 'Creates a new task card on the Trello board under a designated status list.',
    category: 'TRELLO',
    version: '1.2.0',
    status: 'ACTIVE',
    requiresApproval: true,
    executorType: 'TrelloCreateCardExecutor',
    tags: ['card', 'create', 'new', 'trello', 'task', 'add'],
    totalExecutions: 84,
    lastExecutedAt: '2026-11-10 16:45',
    parametersSchema: {
      type: 'object',
      properties: {
        name: { type: 'string', description: 'Title of the task card to create.' },
        list_name: { type: 'string', description: 'Destination list (TODO, IN_PROGRESS, IN_REVIEW, DONE).' },
        description: { type: 'string', description: 'Detailed markdown card description.' },
        due_date: { type: 'string', description: 'Optional due date in ISO 8601 format.' },
        member_name: { type: 'string', description: 'Optional team member assignee name.' }
      },
      required: ['name']
    }
  },
  {
    id: 'TOOL-002',
    name: 'trello_move_card',
    description: 'Transitions an existing card to another list (e.g. TODO, IN_PROGRESS, IN_REVIEW, DONE).',
    category: 'TRELLO',
    version: '1.1.0',
    status: 'ACTIVE',
    requiresApproval: true,
    executorType: 'TrelloMoveCardExecutor',
    tags: ['card', 'move', 'status', 'transition', 'workflow'],
    totalExecutions: 142,
    lastExecutedAt: '2026-11-10 17:12',
    parametersSchema: {
      type: 'object',
      properties: {
        card_title: { type: 'string', description: 'Title or identifier of card to move.' },
        card_id: { type: 'string', description: 'Explicit Trello card ID.' },
        target_list: { type: 'string', enum: ['TODO', 'IN_PROGRESS', 'IN_REVIEW', 'DONE'], description: 'Destination list.' }
      },
      required: ['target_list']
    }
  },
  {
    id: 'TOOL-003',
    name: 'trello_update_card',
    description: 'Updates card title, description, or due date on Trello.',
    category: 'TRELLO',
    version: '1.0.4',
    status: 'ACTIVE',
    requiresApproval: true,
    executorType: 'TrelloUpdateCardExecutor',
    tags: ['card', 'update', 'edit', 'modify', 'due_date'],
    totalExecutions: 56,
    lastExecutedAt: '2026-11-09 11:20',
    parametersSchema: {
      type: 'object',
      properties: {
        card_title: { type: 'string', description: 'Target card title.' },
        new_title: { type: 'string', description: 'New headline.' },
        new_due_date: { type: 'string', description: 'New deadline.' }
      }
    }
  },
  {
    id: 'TOOL-004',
    name: 'trello_delete_card',
    description: 'Permanently deletes or archives an existing card from Trello.',
    category: 'TRELLO',
    version: '1.0.0',
    status: 'ACTIVE',
    requiresApproval: true,
    executorType: 'TrelloDeleteCardExecutor',
    tags: ['card', 'delete', 'archive', 'destroy'],
    totalExecutions: 19,
    lastExecutedAt: '2026-11-08 09:14',
    parametersSchema: {
      type: 'object',
      properties: {
        card_title: { type: 'string', description: 'Title of the card to delete.' },
        card_id: { type: 'string', description: 'Card ID.' }
      }
    }
  },
  {
    id: 'TOOL-005',
    name: 'trello_search_cards',
    description: 'Searches for cards matching keywords, list status, or assigned employee.',
    category: 'TRELLO',
    version: '2.0.1',
    status: 'ACTIVE',
    requiresApproval: false,
    executorType: 'TrelloSearchCardsExecutor',
    tags: ['search', 'find', 'lookup', 'cards', 'filter'],
    totalExecutions: 312,
    lastExecutedAt: '2026-11-10 17:40',
    parametersSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Keyword query.' },
        status: { type: 'string', description: 'Status list name.' },
        assignee: { type: 'string', description: 'Employee name.' }
      }
    }
  },
  {
    id: 'TOOL-006',
    name: 'report_get_workload',
    description: 'Calculates pure-Python workload rollups, completion rates, and status distributions.',
    category: 'REPORTING',
    version: '1.3.0',
    status: 'ACTIVE',
    requiresApproval: false,
    executorType: 'ReportGetWorkloadExecutor',
    tags: ['report', 'workload', 'daily', 'weekly', 'metrics', 'aggregations'],
    totalExecutions: 95,
    lastExecutedAt: '2026-11-10 14:00',
    parametersSchema: {
      type: 'object',
      properties: {
        report_type: { type: 'string', enum: ['daily', 'weekly', 'custom'], default: 'daily' },
        employee_id: { type: 'string', description: 'Optional employee identifier.' },
        start_date: { type: 'string', description: 'Start date (YYYY-MM-DD).' },
        end_date: { type: 'string', description: 'End date (YYYY-MM-DD).' }
      }
    }
  },
  {
    id: 'TOOL-007',
    name: 'report_get_employee_tasks',
    description: 'Retrieves employee task assignments and distinguishes active IN_PROGRESS work from overall assignees.',
    category: 'EMPLOYEE',
    version: '1.1.2',
    status: 'ACTIVE',
    requiresApproval: false,
    executorType: 'ReportGetEmployeeTasksExecutor',
    tags: ['employee', 'tasks', 'active', 'in_progress', 'roster'],
    totalExecutions: 110,
    lastExecutedAt: '2026-11-10 15:30',
    parametersSchema: {
      type: 'object',
      properties: {
        employee_name: { type: 'string', description: 'Employee name.' },
        status_filter: { type: 'string', description: 'Status filter.' }
      }
    }
  },
  {
    id: 'TOOL-008',
    name: 'analytics_team_velocity',
    description: 'Computes rolling 14-day completion velocity across engineering departments.',
    category: 'ANALYTICS',
    version: '1.0.0',
    status: 'ACTIVE',
    requiresApproval: false,
    executorType: 'AnalyticsTeamVelocityExecutor',
    tags: ['analytics', 'velocity', 'trend', 'productivity'],
    totalExecutions: 48,
    lastExecutedAt: '2026-11-09 23:59',
    parametersSchema: {
      type: 'object',
      properties: {
        department: { type: 'string', description: 'Department name.' }
      }
    }
  },
  {
    id: 'TOOL-009',
    name: 'system_cleanup_expired_actions',
    description: 'Maintenance tool to purge expired pending actions beyond TTL window.',
    category: 'SYSTEM',
    version: '1.0.0',
    status: 'ACTIVE',
    requiresApproval: true,
    executorType: 'SystemCleanupExpiredActionsExecutor',
    tags: ['system', 'cleanup', 'maintenance', 'ttl'],
    totalExecutions: 24,
    lastExecutedAt: '2026-11-10 03:00',
    parametersSchema: {
      type: 'object',
      properties: {
        older_than_hours: { type: 'integer', default: 24 }
      }
    }
  },
  {
    id: 'TOOL-010',
    name: 'legacy_trello_v1_sync',
    description: 'Deprecated legacy sync connector for Trello v1 boards.',
    category: 'TRELLO',
    version: '0.9.1',
    status: 'DISABLED',
    requiresApproval: true,
    executorType: 'LegacyTrelloSyncExecutor',
    tags: ['deprecated', 'legacy', 'v1'],
    totalExecutions: 5,
    lastExecutedAt: '2026-10-15 12:00',
    parametersSchema: {
      type: 'object',
      properties: {
        legacy_key: { type: 'string' }
      }
    }
  }
];


import { ChatMessage } from '../types';

export const INITIAL_MOCK_CHAT: ChatMessage[] = [
  {
    id: 'MSG-001',
    sender: 'user',
    content: 'Show me overdue tasks across all engineering teams.',
    timestamp: '10:24 AM',
  },
  {
    id: 'MSG-002',
    sender: 'assistant',
    content: 'I analyzed current board activities. There is currently 1 overdue task: "Migrate Legacy REST Auth to Bearer Token Header" (Assigned to Sarah Connor, due on Nov 5).',
    timestamp: '10:24 AM',
    discoveredTool: {
      name: 'report_get_workload',
      category: 'REPORTING',
      relevanceScore: 0.94,
      explanation: 'Discovered reporting aggregation tool to compute overdue task statistics.',
    },
    executionStatus: 'EXECUTED',
  },
  {
    id: 'MSG-003',
    sender: 'user',
    content: 'Add a card named Login API',
    timestamp: '10:28 AM',
  },
  {
    id: 'MSG-004',
    sender: 'assistant',
    content: 'I have prepared the following action for your preview. Because this action mutates your Trello board, it requires explicit confirmation.',
    timestamp: '10:28 AM',
    discoveredTool: {
      name: 'trello_create_card',
      category: 'TRELLO',
      relevanceScore: 0.98,
      explanation: 'Interpreted intent as a card creation mutation on designated board list.',
    },
    approvalPreview: {
      actionId: 'ACT-PREVIEW-9842',
      actionType: 'CREATE_CARD',
      targetEntity: 'Trello Card',
      cardName: 'Login API',
      boardName: 'Engineering Sprint Board',
      listName: 'TODO',
      parameters: {
        name: 'Login API',
        list_name: 'TODO',
        description: 'Auto-generated task from natural language command.',
        priority: 'MEDIUM',
      },
      status: 'PENDING',
      createdAt: '2026-11-10 10:28:14',
    },
    executionStatus: 'AWAITING_APPROVAL',
  },
];


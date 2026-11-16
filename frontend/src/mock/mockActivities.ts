import { ActivityEvent } from '../types';

export const MOCK_ACTIVITIES: ActivityEvent[] = [
  {
    id: 'ACT-001',
    eventType: 'CARD_MOVED',
    actor: {
      name: 'Sarah Connor',
      avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&h=100&fit=crop&crop=faces',
    },
    cardTitle: 'Pending Action Hash Tamper-Proofing',
    cardId: 'TASK-105',
    details: 'Moved card from IN_REVIEW to DONE after human approval verification.',
    timestamp: '12 minutes ago',
    statusChange: {
      from: 'IN_REVIEW',
      to: 'DONE',
    },
  },
  {
    id: 'ACT-002',
    eventType: 'CARD_CREATED',
    actor: {
      name: 'Agentic AI (Assistant)',
      avatar: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=100&h=100&fit=crop&crop=faces',
    },
    cardTitle: 'Fix Card Description Sanitizer for Gemini LLM',
    cardId: 'TASK-112',
    details: 'Created card on list IN_PROGRESS following natural language command.',
    timestamp: '45 minutes ago',
  },
  {
    id: 'ACT-003',
    eventType: 'EMPLOYEE_ASSIGNED',
    actor: {
      name: 'Alex Rivera',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&h=100&fit=crop&crop=faces',
    },
    cardTitle: 'Design Dark & Light Theme SaaS Dashboard',
    cardId: 'TASK-106',
    details: 'Assigned task to Liam Chen.',
    timestamp: '2 hours ago',
  },
  {
    id: 'ACT-004',
    eventType: 'CARD_MOVED',
    actor: {
      name: 'Liam Chen',
      avatar: 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=100&h=100&fit=crop&crop=faces',
    },
    cardTitle: 'Design Dark & Light Theme SaaS Dashboard',
    cardId: 'TASK-106',
    details: 'Transitioned card from IN_PROGRESS to IN_REVIEW.',
    timestamp: '3 hours ago',
    statusChange: {
      from: 'IN_PROGRESS',
      to: 'IN_REVIEW',
    },
  },
  {
    id: 'ACT-005',
    eventType: 'TASK_COMPLETED',
    actor: {
      name: 'Elena Rostova',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop&crop=faces',
    },
    cardTitle: 'Employee Workload Calculation Engine',
    cardId: 'TASK-104',
    details: 'Completed unit test coverage and passed performance verification.',
    timestamp: '5 hours ago',
    statusChange: {
      from: 'IN_REVIEW',
      to: 'DONE',
    },
  },
  {
    id: 'ACT-006',
    eventType: 'CARD_UPDATED',
    actor: {
      name: 'Marcus Vance',
      avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100&h=100&fit=crop&crop=faces',
    },
    cardTitle: 'Trello Webhook Sync for Move Events',
    cardId: 'TASK-103',
    details: 'Updated card due date to 2026-11-10.',
    timestamp: 'Yesterday at 17:30',
  },
  {
    id: 'ACT-007',
    eventType: 'CARD_CREATED',
    actor: {
      name: 'Chloe Bennett',
      avatar: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=100&h=100&fit=crop&crop=faces',
    },
    cardTitle: 'Audit Trail Export to CSV / JSON',
    cardId: 'TASK-109',
    details: 'Drafted compliance task card in list TODO.',
    timestamp: 'Yesterday at 14:15',
  }
];


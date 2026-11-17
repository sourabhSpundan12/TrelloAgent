import React, { createContext, useContext, useEffect, useState } from 'react';
import { Board } from '../types';
import {
  activateBoard as apiActivateBoard,
  deactivateBoard as apiDeactivateBoard,
  toggleBoardStatus as apiToggleBoardStatus,
  addBoard as apiAddBoard,
  deleteBoard as apiDeleteBoard,
  fetchBoards,
  getStoredToken,
} from '../services/api';

interface BoardContextType {
  boards: Board[];
  activeBoard: Board | null;
  activeBoardId: string;
  isLoading: boolean;
  error: string | null;
  activateBoard: (boardId: string) => Promise<void>;
  deactivateBoard: (boardId: string) => Promise<void>;
  toggleBoardStatus: (boardId: string) => Promise<void>;
  addBoard: (boardId: string, name?: string, desc?: string) => Promise<Board>;
  deleteBoard: (boardId: string) => Promise<void>;
  refreshBoards: () => Promise<void>;
}

const BoardContext = createContext<BoardContextType | undefined>(undefined);

const ACTIVE_BOARD_KEY = 'atm_active_board_id';

export const BoardProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [boards, setBoards] = useState<Board[]>([]);
  const [activeBoard, setActiveBoard] = useState<Board | null>(null);
  const [activeBoardId, setActiveBoardId] = useState<string>(() => {
    return localStorage.getItem(ACTIVE_BOARD_KEY) || '';
  });
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadBoards = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const token = getStoredToken();
      const res = await fetchBoards(token || undefined);
      const list = res.boards || [];
      setBoards(list);

      const active = list.find((b) => b.is_active) || null;
      setActiveBoard(active);
      if (active) {
        setActiveBoardId(active.board_id);
        localStorage.setItem(ACTIVE_BOARD_KEY, active.board_id);
      } else {
        setActiveBoardId('');
        localStorage.removeItem(ACTIVE_BOARD_KEY);
      }
    } catch (err: any) {
      console.warn('Could not load boards:', err);
      setError(err?.response?.data?.detail || err?.message || 'Failed to load boards');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadBoards();
  }, []);

  const activateBoard = async (boardId: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const token = getStoredToken();
      const updated = await apiActivateBoard(boardId, token || undefined);

      setBoards((prev) =>
        prev.map((b) => ({
          ...b,
          is_active: b.board_id === boardId,
        }))
      );
      setActiveBoard(updated);
      setActiveBoardId(boardId);
      localStorage.setItem(ACTIVE_BOARD_KEY, boardId);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to activate board';
      setError(msg);
      throw new Error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const deactivateBoard = async (boardId: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const token = getStoredToken();
      await apiDeactivateBoard(boardId, token || undefined);

      setBoards((prev) =>
        prev.map((b) => (b.board_id === boardId ? { ...b, is_active: false } : b))
      );
      if (activeBoardId === boardId) {
        setActiveBoard(null);
        setActiveBoardId('');
        localStorage.removeItem(ACTIVE_BOARD_KEY);
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to deactivate board';
      setError(msg);
      throw new Error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleBoardStatus = async (boardId: string) => {
    const target = boards.find((b) => b.board_id === boardId);
    if (target?.is_active) {
      await deactivateBoard(boardId);
    } else {
      await activateBoard(boardId);
    }
  };

  const addBoard = async (boardId: string, name?: string, desc?: string): Promise<Board> => {
    try {
      setIsLoading(true);
      setError(null);
      const token = getStoredToken();
      const newBoard = await apiAddBoard(
        { board_id: boardId.trim(), name: name?.trim(), desc: desc?.trim() },
        token || undefined
      );

      // Refresh full board list from server to guarantee sync
      await loadBoards();
      return newBoard;
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to add board';
      setError(msg);
      throw new Error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const deleteBoard = async (boardId: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const token = getStoredToken();
      await apiDeleteBoard(boardId, token || undefined);

      setBoards((prev) => prev.filter((b) => b.board_id !== boardId));

      if (activeBoardId === boardId) {
        await loadBoards();
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to delete board';
      setError(msg);
      throw new Error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const refreshBoards = async () => {
    await loadBoards();
  };

  return (
    <BoardContext.Provider
      value={{
        boards,
        activeBoard,
        activeBoardId,
        isLoading,
        error,
        activateBoard,
        deactivateBoard,
        toggleBoardStatus,
        addBoard,
        deleteBoard,
        refreshBoards,
      }}
    >
      {children}
    </BoardContext.Provider>
  );
};

export const useBoard = (): BoardContextType => {
  const context = useContext(BoardContext);
  if (!context) {
    throw new Error('useBoard must be used within a BoardProvider');
  }
  return context;
};

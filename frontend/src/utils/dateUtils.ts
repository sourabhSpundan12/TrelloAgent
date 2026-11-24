/**
 * Shared Date & Time Utilities with strict IST (Indian Standard Time, UTC+5:30) formatting.
 */

export const IST_TIMEZONE = 'Asia/Kolkata';

export function formatISTDate(dateInput?: string | number | Date | null): string {
  if (!dateInput) return '—';
  try {
    const d = typeof dateInput === 'string' || typeof dateInput === 'number' ? new Date(dateInput) : dateInput;
    if (isNaN(d.getTime())) return String(dateInput);
    return d.toLocaleDateString('en-US', {
      timeZone: IST_TIMEZONE,
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return String(dateInput);
  }
}

export function formatISTTime(dateInput?: string | number | Date | null): string {
  if (!dateInput) return '';
  try {
    const d = typeof dateInput === 'string' || typeof dateInput === 'number' ? new Date(dateInput) : dateInput;
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('en-US', {
      timeZone: IST_TIMEZONE,
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return '';
  }
}

export function formatISTDateTime(dateInput?: string | number | Date | null): string {
  if (!dateInput) return '—';
  try {
    const d = typeof dateInput === 'string' || typeof dateInput === 'number' ? new Date(dateInput) : dateInput;
    if (isNaN(d.getTime())) return String(dateInput);
    return d.toLocaleString('en-US', {
      timeZone: IST_TIMEZONE,
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return String(dateInput);
  }
}


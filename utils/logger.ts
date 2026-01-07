/**
 * Frontend logging utility with timestamps
 * Formats logs with timestamps for synchronization with backend
 */

export function getTimestamp(): string {
  const now = new Date();
  const hours = now.getHours().toString().padStart(2, '0');
  const minutes = now.getMinutes().toString().padStart(2, '0');
  const seconds = now.getSeconds().toString().padStart(2, '0');
  const milliseconds = now.getMilliseconds().toString().padStart(3, '0');
  return `${hours}:${minutes}:${seconds}.${milliseconds}`;
}

export function logWithTimestamp(message: string, ...args: any[]): void {
  const timestamp = getTimestamp();
  console.log(`[${timestamp}] ${message}`, ...args);
}

export function warnWithTimestamp(message: string, ...args: any[]): void {
  const timestamp = getTimestamp();
  console.warn(`[${timestamp}] ${message}`, ...args);
}

export function errorWithTimestamp(message: string, ...args: any[]): void {
  const timestamp = getTimestamp();
  console.error(`[${timestamp}] ${message}`, ...args);
}


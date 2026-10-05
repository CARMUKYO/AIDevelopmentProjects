import type { NextFunction, Request, Response } from 'express';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

export function notFoundHandler(_req: Request, res: Response, _next: NextFunction): void {
  res.status(404).json({ error: { code: 'not_found', message: 'Route not found' } });
}

export function errorHandler(
  err: unknown,
  _req: Request,
  res: Response,
  _next: NextFunction,
): void {
  if (err instanceof ApiError) {
    res.status(err.status).json({
      error: {
        code: err.code,
        message: err.message,
        ...(err.details !== undefined ? { details: err.details } : {}),
      },
    });
    return;
  }
  if (err instanceof SyntaxError && (err as { status?: number }).status === 400) {
    res.status(400).json({ error: { code: 'invalid_json', message: 'Malformed JSON body' } });
    return;
  }
  console.error(err);
  res.status(500).json({ error: { code: 'internal_error', message: 'Unexpected error' } });
}

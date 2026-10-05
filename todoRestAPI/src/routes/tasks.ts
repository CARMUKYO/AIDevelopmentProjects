import { Router } from 'express';
import type Database from 'better-sqlite3';
import {
  createTaskSchema,
  listQuerySchema,
  patchTaskSchema,
  putTaskSchema,
  taskParamsSchema,
  toTaskDto,
  type TaskRow,
} from '../schemas.js';
import { ApiError } from '../errors.js';

interface Issue {
  path: string;
  message: string;
}

function validationError(message: string, issues: Issue[]): ApiError {
  return new ApiError(400, 'validation_error', message, issues);
}

function toIssues(error: { issues: { path: (string | number)[]; message: string }[] }): Issue[] {
  return error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message }));
}

function getTaskOrThrow(db: Database.Database, id: number): TaskRow {
  const row = db.prepare('SELECT * FROM tasks WHERE id = ?').get(id) as TaskRow | undefined;
  if (row === undefined) {
    throw new ApiError(404, 'task_not_found', `Task ${id} not found`);
  }
  return row;
}

function selectTask(db: Database.Database, id: number): TaskRow {
  return db.prepare('SELECT * FROM tasks WHERE id = ?').get(id) as TaskRow;
}

export function tasksRouter(db: Database.Database): Router {
  const router = Router();

  router.get('/', (req, res, next) => {
    const parsed = listQuerySchema.safeParse(req.query);
    if (!parsed.success) {
      next(validationError('Invalid query parameters', toIssues(parsed.error)));
      return;
    }
    const { completed, limit, offset } = parsed.data;
    const where = completed === undefined ? '' : 'WHERE completed = ?';
    const filterValues: number[] = completed === undefined ? [] : [completed ? 1 : 0];
    const totalRow = db
      .prepare(`SELECT COUNT(*) AS count FROM tasks ${where}`)
      .get(...filterValues) as { count: number };
    const rows = db
      .prepare(`SELECT * FROM tasks ${where} ORDER BY id DESC LIMIT ? OFFSET ?`)
      .all(...filterValues, limit, offset) as TaskRow[];
    res.json({ data: rows.map(toTaskDto), limit, offset, total: totalRow.count });
  });

  router.post('/', (req, res, next) => {
    const parsed = createTaskSchema.safeParse(req.body);
    if (!parsed.success) {
      next(validationError('Invalid request body', toIssues(parsed.error)));
      return;
    }
    const now = new Date().toISOString();
    const info = db
      .prepare(
        'INSERT INTO tasks (title, description, completed, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
      )
      .run(
        parsed.data.title,
        parsed.data.description ?? null,
        parsed.data.completed ? 1 : 0,
        now,
        now,
      );
    res
      .status(201)
      .location(`/api/v1/tasks/${info.lastInsertRowid}`)
      .json(toTaskDto(selectTask(db, Number(info.lastInsertRowid))));
  });

  router.get('/:id', (req, res, next) => {
    const parsed = taskParamsSchema.safeParse(req.params);
    if (!parsed.success) {
      next(validationError('Invalid task id', toIssues(parsed.error)));
      return;
    }
    res.json(toTaskDto(getTaskOrThrow(db, parsed.data.id)));
  });

  router.patch('/:id', (req, res, next) => {
    const params = taskParamsSchema.safeParse(req.params);
    if (!params.success) {
      next(validationError('Invalid task id', toIssues(params.error)));
      return;
    }
    getTaskOrThrow(db, params.data.id);
    const parsed = patchTaskSchema.safeParse(req.body);
    if (!parsed.success) {
      next(validationError('Invalid request body', toIssues(parsed.error)));
      return;
    }
    // Columns come from a fixed allowlist and values are bound, so this is safe to build.
    const assignments: string[] = [];
    const values: (string | number | null)[] = [];
    if (parsed.data.title !== undefined) {
      assignments.push('title = ?');
      values.push(parsed.data.title);
    }
    if (parsed.data.description !== undefined) {
      assignments.push('description = ?');
      values.push(parsed.data.description);
    }
    if (parsed.data.completed !== undefined) {
      assignments.push('completed = ?');
      values.push(parsed.data.completed ? 1 : 0);
    }
    assignments.push('updated_at = ?');
    values.push(new Date().toISOString(), params.data.id);
    db.prepare(`UPDATE tasks SET ${assignments.join(', ')} WHERE id = ?`).run(...values);
    res.json(toTaskDto(selectTask(db, params.data.id)));
  });

  router.put('/:id', (req, res, next) => {
    const params = taskParamsSchema.safeParse(req.params);
    if (!params.success) {
      next(validationError('Invalid task id', toIssues(params.error)));
      return;
    }
    getTaskOrThrow(db, params.data.id);
    if (req.body !== null && typeof req.body === 'object' && 'completed' in req.body) {
      next(new ApiError(400, 'validation_error', 'completed is PATCH-only; omit it from PUT'));
      return;
    }
    const parsed = putTaskSchema.safeParse(req.body);
    if (!parsed.success) {
      next(validationError('Invalid request body', toIssues(parsed.error)));
      return;
    }
    db.prepare('UPDATE tasks SET title = ?, description = ?, updated_at = ? WHERE id = ?').run(
      parsed.data.title,
      parsed.data.description ?? null,
      new Date().toISOString(),
      params.data.id,
    );
    res.json(toTaskDto(selectTask(db, params.data.id)));
  });

  router.delete('/:id', (req, res, next) => {
    const parsed = taskParamsSchema.safeParse(req.params);
    if (!parsed.success) {
      next(validationError('Invalid task id', toIssues(parsed.error)));
      return;
    }
    getTaskOrThrow(db, parsed.data.id);
    db.prepare('DELETE FROM tasks WHERE id = ?').run(parsed.data.id);
    res.status(204).send();
  });

  return router;
}

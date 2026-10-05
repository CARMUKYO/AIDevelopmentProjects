import express from 'express';
import type Database from 'better-sqlite3';
import { tasksRouter } from './routes/tasks.js';
import { errorHandler, notFoundHandler } from './errors.js';

export function createApp(db: Database.Database): express.Express {
  const app = express();
  app.use(express.json());
  app.use('/api/v1/tasks', tasksRouter(db));
  app.use(notFoundHandler);
  app.use(errorHandler);
  return app;
}

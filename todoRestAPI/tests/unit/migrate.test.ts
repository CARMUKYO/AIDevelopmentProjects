import { describe, expect, it } from 'vitest';
import Database from 'better-sqlite3';
import { migrate } from '../../src/db/migrate.js';

describe('migrate', () => {
  it('applies pending migrations and is idempotent', () => {
    const db = new Database(':memory:');

    expect(migrate(db)).toEqual(['001_create_tasks.sql']);
    expect(migrate(db)).toEqual([]);

    const tables = db
      .prepare("SELECT name FROM sqlite_master WHERE type = 'table'")
      .all() as { name: string }[];
    expect(tables.map((table) => table.name).sort()).toEqual(['_migrations', 'sqlite_sequence', 'tasks']);

    db.close();
  });
});

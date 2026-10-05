import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type Database from 'better-sqlite3';
import { openDatabase } from './connection.js';

const MIGRATIONS_DIR = process.env.MIGRATIONS_DIR ?? join(process.cwd(), 'migrations');

export function migrate(db: Database.Database, dir: string = MIGRATIONS_DIR): string[] {
  db.exec(
    'CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)',
  );
  const applied = new Set(
    (db.prepare('SELECT name FROM _migrations').all() as { name: string }[]).map(
      (row) => row.name,
    ),
  );
  const files = readdirSync(dir)
    .filter((file) => file.endsWith('.sql'))
    .sort();
  const insert = db.prepare(
    "INSERT INTO _migrations (name, applied_at) VALUES (?, datetime('now'))",
  );
  const apply = db.transaction((name: string, sql: string) => {
    db.exec(sql);
    insert.run(name);
  });
  const newlyApplied: string[] = [];
  for (const file of files) {
    if (applied.has(file)) {
      continue;
    }
    apply(file, readFileSync(join(dir, file), 'utf8'));
    newlyApplied.push(file);
  }
  return newlyApplied;
}

const invokedDirectly =
  process.argv[1] !== undefined && fileURLToPath(import.meta.url) === process.argv[1];

if (invokedDirectly) {
  const db = openDatabase();
  const applied = migrate(db);
  console.log(applied.length === 0 ? 'No new migrations.' : `Applied: ${applied.join(', ')}`);
  db.close();
}

import { afterEach, describe, expect, it } from 'vitest';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { openDatabase } from '../../src/db/connection.js';

describe('openDatabase', () => {
  const dirs: string[] = [];

  afterEach(() => {
    for (const dir of dirs.splice(0)) {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('creates parent directories and opens a working file database', () => {
    const dir = mkdtempSync(join(tmpdir(), 'todo-test-'));
    dirs.push(dir);
    const path = join(dir, 'nested', 'todo.db');

    const db = openDatabase(path);
    db.exec('CREATE TABLE probe (id INTEGER)');
    expect(db.prepare('SELECT count(*) AS n FROM probe').get()).toEqual({ n: 0 });
    db.close();
  });

  it('opens an in-memory database without touching the filesystem', () => {
    const db = openDatabase(':memory:');
    db.exec('CREATE TABLE probe (id INTEGER)');
    db.close();
  });
});

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import Database from 'better-sqlite3';
import request from 'supertest';
import type { Express } from 'express';
import { migrate } from '../../src/db/migrate.js';
import { createApp } from '../../src/app.js';

function setup(): { db: Database.Database; app: Express } {
  const db = new Database(':memory:');
  migrate(db);
  return { db, app: createApp(db) };
}

describe('tasks API (slice 1)', () => {
  let db: Database.Database;
  let app: Express;

  beforeEach(() => {
    ({ db, app } = setup());
  });

  afterEach(() => {
    db.close();
  });

  it('POST creates a task and returns 201 with a Location header', async () => {
    const res = await request(app)
      .post('/api/v1/tasks')
      .send({ title: 'Buy milk', description: '2% or oat' })
      .expect(201);

    expect(res.headers.location).toBe(`/api/v1/tasks/${res.body.id}`);
    expect(res.body).toMatchObject({
      id: expect.any(Number),
      title: 'Buy milk',
      description: '2% or oat',
      completed: false,
    });
    expect(typeof res.body.created_at).toBe('string');
    expect(typeof res.body.updated_at).toBe('string');
  });

  it('POST rejects an invalid body with the 400 error shape', async () => {
    const res = await request(app).post('/api/v1/tasks').send({ title: '' }).expect(400);

    expect(res.body.error.code).toBe('validation_error');
    expect(typeof res.body.error.message).toBe('string');
    expect(Array.isArray(res.body.error.details)).toBe(true);
  });

  it('POST rejects malformed JSON with the 400 error shape', async () => {
    const res = await request(app)
      .post('/api/v1/tasks')
      .set('Content-Type', 'application/json')
      .send('{"title": broken')
      .expect(400);

    expect(res.body.error.code).toBe('invalid_json');
  });

  it('GET returns an empty envelope when no tasks exist', async () => {
    const res = await request(app).get('/api/v1/tasks').expect(200);
    expect(res.body).toEqual({ data: [], limit: 20, offset: 0, total: 0 });
  });

  it('GET returns tasks newest first', async () => {
    await request(app).post('/api/v1/tasks').send({ title: 'first' }).expect(201);
    await request(app).post('/api/v1/tasks').send({ title: 'second' }).expect(201);

    const res = await request(app).get('/api/v1/tasks').expect(200);
    expect(res.body.data.map((task: { title: string }) => task.title)).toEqual([
      'second',
      'first',
    ]);
    expect(res.body.total).toBe(2);
  });

  it('unknown routes return the 404 error shape', async () => {
    const res = await request(app).get('/api/v1/nope').expect(404);
    expect(res.body.error.code).toBe('not_found');
  });
});

describe('tasks API (slice 2)', () => {
  let db: Database.Database;
  let app: Express;

  beforeEach(() => {
    ({ db, app } = setup());
  });

  afterEach(() => {
    db.close();
  });

  it('GET returns a single task by id', async () => {
    const created = await request(app).post('/api/v1/tasks').send({ title: 'find me' }).expect(201);

    const res = await request(app).get(`/api/v1/tasks/${created.body.id}`).expect(200);
    expect(res.body).toMatchObject({ id: created.body.id, title: 'find me', completed: false });
  });

  it('GET returns 404 with the error shape for an unknown id', async () => {
    const res = await request(app).get('/api/v1/tasks/999').expect(404);
    expect(res.body.error.code).toBe('task_not_found');
    expect(typeof res.body.error.message).toBe('string');
  });

  it('GET returns 400 for a malformed id', async () => {
    const res = await request(app).get('/api/v1/tasks/abc').expect(400);
    expect(res.body.error.code).toBe('validation_error');
  });

  it('DELETE removes a task and returns 204', async () => {
    const created = await request(app).post('/api/v1/tasks').send({ title: 'gone soon' }).expect(201);

    await request(app).delete(`/api/v1/tasks/${created.body.id}`).expect(204);
    await request(app).get(`/api/v1/tasks/${created.body.id}`).expect(404);

    const list = await request(app).get('/api/v1/tasks').expect(200);
    expect(list.body.data).toEqual([]);
    expect(list.body.total).toBe(0);
  });

  it('DELETE returns 404 for an unknown id', async () => {
    const res = await request(app).delete('/api/v1/tasks/999').expect(404);
    expect(res.body.error.code).toBe('task_not_found');
  });

  it('DELETE returns 400 for a malformed id', async () => {
    const res = await request(app).delete('/api/v1/tasks/abc').expect(400);
    expect(res.body.error.code).toBe('validation_error');
  });
});

describe('tasks API (slice 3)', () => {
  let db: Database.Database;
  let app: Express;

  beforeEach(() => {
    ({ db, app } = setup());
  });

  afterEach(() => {
    db.close();
  });

  it('PATCH updates only the given fields', async () => {
    const created = await request(app)
      .post('/api/v1/tasks')
      .send({ title: 'original', description: 'keep me' })
      .expect(201);

    const res = await request(app)
      .patch(`/api/v1/tasks/${created.body.id}`)
      .send({ title: 'renamed' })
      .expect(200);

    expect(res.body).toMatchObject({
      id: created.body.id,
      title: 'renamed',
      description: 'keep me',
      completed: false,
    });
  });

  it('PATCH flips the completed flag both ways', async () => {
    const created = await request(app).post('/api/v1/tasks').send({ title: 'chore' }).expect(201);

    const done = await request(app)
      .patch(`/api/v1/tasks/${created.body.id}`)
      .send({ completed: true })
      .expect(200);
    expect(done.body.completed).toBe(true);

    const undone = await request(app)
      .patch(`/api/v1/tasks/${created.body.id}`)
      .send({ completed: false })
      .expect(200);
    expect(undone.body.completed).toBe(false);
  });

  it('PATCH rejects an empty body', async () => {
    const created = await request(app).post('/api/v1/tasks').send({ title: 't' }).expect(201);

    const res = await request(app).patch(`/api/v1/tasks/${created.body.id}`).send({}).expect(400);
    expect(res.body.error.code).toBe('validation_error');
  });

  it('PATCH rejects an invalid title', async () => {
    const created = await request(app).post('/api/v1/tasks').send({ title: 't' }).expect(201);

    const res = await request(app)
      .patch(`/api/v1/tasks/${created.body.id}`)
      .send({ title: '' })
      .expect(400);
    expect(res.body.error.code).toBe('validation_error');
  });

  it('PATCH returns 404 for an unknown id', async () => {
    const res = await request(app).patch('/api/v1/tasks/999').send({ title: 'x' }).expect(404);
    expect(res.body.error.code).toBe('task_not_found');
  });

  it('PUT replaces the task and clears an omitted description', async () => {
    const created = await request(app)
      .post('/api/v1/tasks')
      .send({ title: 'old', description: 'stale' })
      .expect(201);
    await request(app)
      .patch(`/api/v1/tasks/${created.body.id}`)
      .send({ completed: true })
      .expect(200);

    const res = await request(app)
      .put(`/api/v1/tasks/${created.body.id}`)
      .send({ title: 'new' })
      .expect(200);

    expect(res.body).toMatchObject({
      id: created.body.id,
      title: 'new',
      description: null,
      completed: true,
    });
  });

  it('PUT rejects a body containing completed', async () => {
    const created = await request(app).post('/api/v1/tasks').send({ title: 't' }).expect(201);

    const res = await request(app)
      .put(`/api/v1/tasks/${created.body.id}`)
      .send({ title: 't', completed: false })
      .expect(400);
    expect(res.body.error.code).toBe('validation_error');
  });

  it('PUT rejects a missing title', async () => {
    const created = await request(app).post('/api/v1/tasks').send({ title: 't' }).expect(201);

    const res = await request(app)
      .put(`/api/v1/tasks/${created.body.id}`)
      .send({ description: 'no title' })
      .expect(400);
    expect(res.body.error.code).toBe('validation_error');
  });

  it('PUT returns 404 for an unknown id', async () => {
    const res = await request(app).put('/api/v1/tasks/999').send({ title: 'x' }).expect(404);
    expect(res.body.error.code).toBe('task_not_found');
  });
});

describe('tasks API (slice 4)', () => {
  let db: Database.Database;
  let app: Express;

  beforeEach(() => {
    ({ db, app } = setup());
  });

  afterEach(() => {
    db.close();
  });

  async function seed(titles: string[]): Promise<number[]> {
    const ids: number[] = [];
    for (const title of titles) {
      const res = await request(app).post('/api/v1/tasks').send({ title }).expect(201);
      ids.push(res.body.id);
    }
    return ids;
  }

  it('filters by completed=true and completed=false', async () => {
    const [first, second] = await seed(['one', 'two']);
    await request(app).patch(`/api/v1/tasks/${first}`).send({ completed: true }).expect(200);

    const done = await request(app).get('/api/v1/tasks?completed=true').expect(200);
    expect(done.body.data.map((task: { id: number }) => task.id)).toEqual([first]);
    expect(done.body.total).toBe(1);

    const open = await request(app).get('/api/v1/tasks?completed=false').expect(200);
    expect(open.body.data.map((task: { id: number }) => task.id)).toEqual([second]);
    expect(open.body.total).toBe(1);
  });

  it('paginates with limit and offset, newest first', async () => {
    await seed(['t1', 't2', 't3', 't4', 't5']);

    const page = await request(app).get('/api/v1/tasks?limit=2&offset=1').expect(200);
    expect(page.body.data.map((task: { title: string }) => task.title)).toEqual(['t4', 't3']);
    expect(page.body).toMatchObject({ limit: 2, offset: 1, total: 5 });
  });

  it('returns an empty page past the end', async () => {
    await seed(['only']);

    const res = await request(app).get('/api/v1/tasks?offset=10').expect(200);
    expect(res.body.data).toEqual([]);
    expect(res.body.total).toBe(1);
  });

  it('rejects bad limit values with 400', async () => {
    for (const limit of ['0', '101', 'abc']) {
      const res = await request(app).get(`/api/v1/tasks?limit=${limit}`).expect(400);
      expect(res.body.error.code).toBe('validation_error');
    }
  });

  it('rejects bad offset values with 400', async () => {
    for (const offset of ['-1', 'abc']) {
      const res = await request(app).get(`/api/v1/tasks?offset=${offset}`).expect(400);
      expect(res.body.error.code).toBe('validation_error');
    }
  });

  it('rejects bad completed values with 400', async () => {
    const res = await request(app).get('/api/v1/tasks?completed=maybe').expect(400);
    expect(res.body.error.code).toBe('validation_error');
  });
});

describe('tasks API (slice 5)', () => {
  let db: Database.Database;
  let app: Express;

  beforeEach(() => {
    ({ db, app } = setup());
  });

  afterEach(() => {
    db.close();
  });

  it('POST accepts an explicit null description', async () => {
    const res = await request(app)
      .post('/api/v1/tasks')
      .send({ title: 't', description: null })
      .expect(201);
    expect(res.body.description).toBeNull();
  });

  it('POST strips unknown fields', async () => {
    const res = await request(app)
      .post('/api/v1/tasks')
      .send({ title: 't', admin: true })
      .expect(201);
    expect(res.body).not.toHaveProperty('admin');
  });

  it('PATCH with a null description clears it', async () => {
    const created = await request(app)
      .post('/api/v1/tasks')
      .send({ title: 't', description: 'stale' })
      .expect(201);

    const res = await request(app)
      .patch(`/api/v1/tasks/${created.body.id}`)
      .send({ description: null })
      .expect(200);
    expect(res.body.description).toBeNull();
  });

  it('PUT with an explicit null description clears it', async () => {
    const created = await request(app)
      .post('/api/v1/tasks')
      .send({ title: 't', description: 'stale' })
      .expect(201);

    const res = await request(app)
      .put(`/api/v1/tasks/${created.body.id}`)
      .send({ title: 't', description: null })
      .expect(200);
    expect(res.body.description).toBeNull();
  });

  it('PATCH bumps updated_at', async () => {
    const created = await request(app).post('/api/v1/tasks').send({ title: 't' }).expect(201);

    const res = await request(app)
      .patch(`/api/v1/tasks/${created.body.id}`)
      .send({ title: 'renamed' })
      .expect(200);
    expect(new Date(res.body.updated_at).getTime()).toBeGreaterThanOrEqual(
      new Date(created.body.created_at).getTime(),
    );
  });

  it('malformed ids include validation details', async () => {
    const res = await request(app).get('/api/v1/tasks/abc').expect(400);
    expect(res.body.error.code).toBe('validation_error');
    expect(res.body.error.details).toHaveLength(1);
    expect(res.body.error.details[0].path).toBe('id');
  });

  it('accepts the maximum limit of 100', async () => {
    const res = await request(app).get('/api/v1/tasks?limit=100').expect(200);
    expect(res.body.limit).toBe(100);
  });

  it('PATCH returns 400 for a malformed id', async () => {
    const res = await request(app).patch('/api/v1/tasks/abc').send({ title: 'x' }).expect(400);
    expect(res.body.error.code).toBe('validation_error');
  });

  it('PUT returns 400 for a malformed id', async () => {
    const res = await request(app).put('/api/v1/tasks/abc').send({ title: 'x' }).expect(400);
    expect(res.body.error.code).toBe('validation_error');
  });

  it('returns 500 with the error shape when the database fails', async () => {
    const broken = new Database(':memory:');
    const brokenApp = createApp(broken);
    broken.close();

    const res = await request(brokenApp).get('/api/v1/tasks').expect(500);
    expect(res.body.error.code).toBe('internal_error');
  });
});

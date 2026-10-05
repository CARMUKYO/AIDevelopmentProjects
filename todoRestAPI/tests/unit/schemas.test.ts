import { describe, expect, it } from 'vitest';
import {
  createTaskSchema,
  listQuerySchema,
  patchTaskSchema,
  putTaskSchema,
  taskParamsSchema,
  toTaskDto,
} from '../../src/schemas.js';

describe('createTaskSchema', () => {
  it('applies defaults for a minimal valid payload', () => {
    expect(createTaskSchema.parse({ title: 'Buy milk' })).toEqual({
      title: 'Buy milk',
      completed: false,
    });
  });

  it('accepts an explicit null description', () => {
    expect(createTaskSchema.parse({ title: 't', description: null })).toEqual({
      title: 't',
      description: null,
      completed: false,
    });
  });

  it('trims the title', () => {
    expect(createTaskSchema.parse({ title: '  spaced  ' }).title).toBe('spaced');
  });

  it('rejects a missing title', () => {
    expect(createTaskSchema.safeParse({}).success).toBe(false);
  });

  it('rejects a blank title', () => {
    expect(createTaskSchema.safeParse({ title: '   ' }).success).toBe(false);
  });

  it('rejects a title longer than 200 characters', () => {
    expect(createTaskSchema.safeParse({ title: 'x'.repeat(201) }).success).toBe(false);
  });

  it('rejects a description longer than 2000 characters', () => {
    expect(
      createTaskSchema.safeParse({ title: 'ok', description: 'x'.repeat(2001) }).success,
    ).toBe(false);
  });
});

describe('taskParamsSchema', () => {
  it('coerces a numeric string id', () => {
    expect(taskParamsSchema.parse({ id: '5' })).toEqual({ id: 5 });
  });

  it('rejects a non-numeric id', () => {
    expect(taskParamsSchema.safeParse({ id: 'abc' }).success).toBe(false);
  });

  it('rejects zero and negative ids', () => {
    expect(taskParamsSchema.safeParse({ id: '0' }).success).toBe(false);
    expect(taskParamsSchema.safeParse({ id: '-2' }).success).toBe(false);
  });

  it('rejects fractional ids', () => {
    expect(taskParamsSchema.safeParse({ id: '2.5' }).success).toBe(false);
  });
});

describe('patchTaskSchema', () => {
  it('accepts a title-only patch', () => {
    expect(patchTaskSchema.parse({ title: 'new title' })).toEqual({ title: 'new title' });
  });

  it('accepts a completion-only patch', () => {
    expect(patchTaskSchema.parse({ completed: true })).toEqual({ completed: true });
  });

  it('accepts a null description so clients can clear it', () => {
    expect(patchTaskSchema.parse({ description: null })).toEqual({ description: null });
  });

  it('rejects an empty patch', () => {
    const result = patchTaskSchema.safeParse({});
    expect(result.success).toBe(false);
  });

  it('rejects an invalid title', () => {
    expect(patchTaskSchema.safeParse({ title: '' }).success).toBe(false);
  });

  it('rejects a non-boolean completed flag', () => {
    expect(patchTaskSchema.safeParse({ completed: 'yes' }).success).toBe(false);
  });
});

describe('putTaskSchema', () => {
  it('accepts a full replacement', () => {
    expect(putTaskSchema.parse({ title: 't', description: 'd' })).toEqual({
      title: 't',
      description: 'd',
    });
  });

  it('leaves an omitted description undefined so the route can clear it', () => {
    expect(putTaskSchema.parse({ title: 't' })).toEqual({ title: 't' });
  });

  it('rejects a missing title', () => {
    expect(putTaskSchema.safeParse({ description: 'd' }).success).toBe(false);
  });

  it('rejects an overlong description', () => {
    expect(putTaskSchema.safeParse({ title: 't', description: 'x'.repeat(2001) }).success).toBe(
      false,
    );
  });
});

describe('listQuerySchema', () => {
  it('applies limit/offset defaults', () => {
    expect(listQuerySchema.parse({})).toEqual({ limit: 20, offset: 0 });
  });

  it('converts completed true/false strings to booleans', () => {
    expect(listQuerySchema.parse({ completed: 'true' }).completed).toBe(true);
    expect(listQuerySchema.parse({ completed: 'false' }).completed).toBe(false);
  });

  it('coerces numeric limit and offset strings', () => {
    expect(listQuerySchema.parse({ limit: '5', offset: '10' })).toEqual({
      limit: 5,
      offset: 10,
    });
  });

  it('rejects out-of-range or non-numeric limits', () => {
    expect(listQuerySchema.safeParse({ limit: '0' }).success).toBe(false);
    expect(listQuerySchema.safeParse({ limit: '101' }).success).toBe(false);
    expect(listQuerySchema.safeParse({ limit: 'abc' }).success).toBe(false);
  });

  it('rejects negative or non-numeric offsets', () => {
    expect(listQuerySchema.safeParse({ offset: '-1' }).success).toBe(false);
    expect(listQuerySchema.safeParse({ offset: 'abc' }).success).toBe(false);
  });

  it('rejects other completed values', () => {
    expect(listQuerySchema.safeParse({ completed: 'maybe' }).success).toBe(false);
  });
});

describe('toTaskDto', () => {
  it('maps 0/1 completed flags to booleans', () => {
    const base = {
      id: 1,
      title: 't',
      description: null,
      created_at: '2026-01-01T00:00:00.000Z',
      updated_at: '2026-01-01T00:00:00.000Z',
    };
    expect(toTaskDto({ ...base, completed: 0 }).completed).toBe(false);
    expect(toTaskDto({ ...base, completed: 1 }).completed).toBe(true);
  });
});

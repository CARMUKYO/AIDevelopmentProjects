import { z } from 'zod';

const titleField = z
  .string()
  .trim()
  .min(1, 'Title is required')
  .max(200, 'Title must be 200 characters or fewer');

const descriptionField = z
  .string()
  .trim()
  .max(2000, 'Description must be 2000 characters or fewer');

export const createTaskSchema = z.object({
  title: titleField,
  description: descriptionField.nullish(),
  completed: z.boolean().optional().default(false),
});

export type CreateTaskInput = z.infer<typeof createTaskSchema>;

export const taskParamsSchema = z.object({
  id: z.coerce.number().int('Task id must be an integer').positive('Task id must be positive'),
});

export type TaskParams = z.infer<typeof taskParamsSchema>;

export const patchTaskSchema = z
  .object({
    title: titleField.optional(),
    description: descriptionField.nullish(),
    completed: z.boolean().optional(),
  })
  .refine((body) => Object.keys(body).length > 0, 'Nothing to update');

export type PatchTaskInput = z.infer<typeof patchTaskSchema>;

export const putTaskSchema = z.object({
  title: titleField,
  description: descriptionField.nullish(),
});

export type PutTaskInput = z.infer<typeof putTaskSchema>;

export const listQuerySchema = z.object({
  completed: z
    .enum(['true', 'false'])
    .transform((value) => value === 'true')
    .optional(),
  limit: z.coerce
    .number()
    .int('limit must be an integer')
    .min(1, 'limit must be at least 1')
    .max(100, 'limit must be 100 or less')
    .default(20),
  offset: z.coerce
    .number()
    .int('offset must be an integer')
    .min(0, 'offset must be 0 or more')
    .default(0),
});

export type ListQuery = z.infer<typeof listQuerySchema>;

export interface TaskRow {
  id: number;
  title: string;
  description: string | null;
  completed: number;
  created_at: string;
  updated_at: string;
}

export interface TaskDto {
  id: number;
  title: string;
  description: string | null;
  completed: boolean;
  created_at: string;
  updated_at: string;
}

export function toTaskDto(row: TaskRow): TaskDto {
  return { ...row, completed: row.completed === 1 };
}

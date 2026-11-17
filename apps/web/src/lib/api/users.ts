import type { UserRole } from "@/types";
import type { components } from "./schema";
import { apiRequest } from "./client";

export type ManagedUser = components["schemas"]["UserOut"];
export interface UsersQuery { page?: number; q?: string; role?: UserRole; isActive?: boolean }
export interface UsersPage { items: ManagedUser[]; total: number; page: number; page_size: number }

export const listUsers = (q: UsersQuery): Promise<UsersPage> =>
  apiRequest("GET /api/v1/admin/users", {
    query: { page: q.page, page_size: 15, q: q.q, role: q.role, is_active: q.isActive },
  });

export const createUser = (body: components["schemas"]["CreateUserRequest"]): Promise<ManagedUser> =>
  apiRequest("POST /api/v1/admin/users", { body });

export const updateUser = (id: string, body: components["schemas"]["UpdateUserRequest"]): Promise<ManagedUser> =>
  apiRequest("PATCH /api/v1/admin/users/{user_id}", { params: { user_id: id }, body });

export const revokeUserSessions = (id: string): Promise<{ revoked: number }> =>
  apiRequest("POST /api/v1/admin/users/{user_id}/sessions/revoke", { params: { user_id: id } });

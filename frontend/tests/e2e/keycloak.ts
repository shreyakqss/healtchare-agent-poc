import { request, type APIRequestContext } from "@playwright/test";

const KEYCLOAK_URL = process.env.KEYCLOAK_URL ?? "http://localhost:8500";
const REALM = "careflow";

export const E2E_USERS = {
  patient: {
    username: "careflow-e2e-patient",
    password: process.env.E2E_USER_PASSWORD ?? "CareFlow-E2E-Only-2026!",
    role: "patient",
  },
  admin: {
    username: "careflow-e2e-admin",
    password: process.env.E2E_USER_PASSWORD ?? "CareFlow-E2E-Only-2026!",
    role: "admin",
  },
} as const;

async function adminContext(): Promise<{ api: APIRequestContext; token: string }> {
  const api = await request.newContext({ baseURL: KEYCLOAK_URL });
  const response = await api.post("/realms/master/protocol/openid-connect/token", {
    form: {
      grant_type: "password",
      client_id: "admin-cli",
      username: process.env.KEYCLOAK_ADMIN_USERNAME ?? "admin",
      password: process.env.KEYCLOAK_ADMIN_PASSWORD ?? "change-me-local",
    },
    timeout: 10_000,
  });
  if (!response.ok()) {
    await api.dispose();
    throw new Error(`Keycloak admin login failed (${response.status()}).`);
  }
  const payload = await response.json() as { access_token?: unknown };
  if (typeof payload.access_token !== "string") {
    await api.dispose();
    throw new Error("Keycloak did not return an admin token.");
  }
  return { api, token: payload.access_token };
}

function adminHeaders(token: string) {
  return { Authorization: `Bearer ${token}`, "content-type": "application/json" };
}

async function userId(api: APIRequestContext, token: string, username: string): Promise<string | null> {
  const response = await api.get(`/admin/realms/${REALM}/users`, {
    headers: adminHeaders(token),
    params: { username, exact: "true" },
    timeout: 10_000,
  });
  if (!response.ok()) throw new Error(`Keycloak user lookup failed (${response.status()}).`);
  const users = await response.json() as Array<{ id?: unknown }>;
  return typeof users[0]?.id === "string" ? users[0].id : null;
}

async function deleteUsers(api: APIRequestContext, token: string): Promise<void> {
  for (const user of Object.values(E2E_USERS)) {
    const id = await userId(api, token, user.username);
    if (!id) continue;
    const response = await api.delete(`/admin/realms/${REALM}/users/${id}`, {
      headers: adminHeaders(token),
      timeout: 10_000,
    });
    if (!response.ok() && response.status() !== 404) {
      throw new Error(`Keycloak test-user cleanup failed (${response.status()}).`);
    }
  }
}

export async function deleteE2eUsers(): Promise<void> {
  const { api, token } = await adminContext();
  try {
    await deleteUsers(api, token);
  } finally {
    await api.dispose();
  }
}

export async function createE2eUsers(): Promise<void> {
  const { api, token } = await adminContext();
  try {
    await deleteUsers(api, token);
    const rolesResponse = await api.get(`/admin/realms/${REALM}/roles`, {
      headers: adminHeaders(token),
      timeout: 10_000,
    });
    if (!rolesResponse.ok()) throw new Error(`Keycloak role lookup failed (${rolesResponse.status()}).`);
    const roles = await rolesResponse.json() as Array<{ id: string; name: string }>;

    for (const user of Object.values(E2E_USERS)) {
      const response = await api.post(`/admin/realms/${REALM}/users`, {
        headers: adminHeaders(token),
        data: {
          username: user.username,
          firstName: "CareFlow",
          lastName: user.role,
          email: `${user.username}@example.test`,
          emailVerified: true,
          enabled: true,
          requiredActions: [],
          credentials: [{ type: "password", value: user.password, temporary: false }],
        },
        timeout: 10_000,
      });
      if (!response.ok()) throw new Error(`Keycloak test-user creation failed (${response.status()}).`);
      const id = await userId(api, token, user.username);
      const role = roles.find((entry) => entry.name === user.role);
      if (!id || !role) throw new Error(`Keycloak ${user.role} role is not available.`);
      const mapping = await api.post(`/admin/realms/${REALM}/users/${id}/role-mappings/realm`, {
        headers: adminHeaders(token),
        data: [role],
        timeout: 10_000,
      });
      if (!mapping.ok()) throw new Error(`Keycloak role assignment failed (${mapping.status()}).`);
    }
  } finally {
    await api.dispose();
  }
}

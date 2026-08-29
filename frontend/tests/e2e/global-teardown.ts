import { deleteE2eUsers } from "./keycloak";

export default async function globalTeardown() {
  await deleteE2eUsers();
}

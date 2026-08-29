import { createE2eUsers } from "./keycloak";

export default async function globalSetup() {
  await createE2eUsers();
}

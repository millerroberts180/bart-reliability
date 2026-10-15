// Distinguishes client instances (e.g. when the dev preview swaps scenarios) so
// request keys from a previous client are never reused.
const clientIds = new WeakMap<object, number>();
let nextClientId = 1;

export function clientKey(client: object): number {
  let id = clientIds.get(client);
  if (id === undefined) {
    id = nextClientId++;
    clientIds.set(client, id);
  }
  return id;
}

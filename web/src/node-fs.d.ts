/**
 * The sandbox this code was written in cannot reach the npm registry, so the Node type
 * declarations (@types/node) are not installed. The only place the web code touches Node is
 * design.test.ts, which reads styles.css off disk to check the design rules. This declares
 * exactly that one module call and nothing else, so the type check stays honest.
 *
 * If @types/node is ever installed, delete this file.
 */
declare module "node:fs" {
  export function readFileSync(path: URL | string, encoding: "utf8"): string;
  export function readdirSync(path: URL | string): string[];
}

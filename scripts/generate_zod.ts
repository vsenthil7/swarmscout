#!/usr/bin/env node
/**
 * Generate zod schemas from the exported JSON Schemas.
 *
 * The hand-curated zod at web/lib/schemas/brief.ts remains the runtime
 * truth during the hackathon (easier to review). This script produces a
 * *check* artefact under web/lib/schemas/generated/*.zod.ts used only by
 * the drift gate in CI — so any Pydantic change that hasn't been mirrored
 * into the hand-curated zod is still caught.
 *
 * Functions:
 *   - fieldZod(schema): map a JSON Schema node to its closest zod expression
 *   - generate(schema): produce a full `export const XSchema = z.object({...})`
 *   - main(): scan every *.schema.json in GEN_DIR and emit a *.zod.ts sibling
 */

const fs = require('node:fs');
const path = require('node:path');

const GEN_DIR = path.resolve(__dirname, '../web/lib/schemas/generated');

function fieldZod(schema) {
  if (!schema) return 'z.unknown()';
  if (schema.$ref) return 'z.unknown()';
  if (schema.enum) return `z.enum([${schema.enum.map((v) => JSON.stringify(v)).join(', ')}])`;
  switch (schema.type) {
    case 'string':
      return 'z.string()';
    case 'integer':
      return 'z.number().int()';
    case 'number':
      return 'z.number()';
    case 'boolean':
      return 'z.boolean()';
    case 'array':
      return `z.array(${fieldZod(schema.items)})`;
    case 'object':
      return 'z.record(z.unknown())';
    default:
      if (Array.isArray(schema.type)) {
        if (schema.type.includes('null')) {
          const other = schema.type.find((t) => t !== 'null');
          return `${fieldZod({ ...schema, type: other })}.nullable()`;
        }
      }
      return 'z.unknown()';
  }
}

function generate(schema) {
  const required = new Set(schema.required || []);
  const lines = ['import { z } from "zod";', '', `export const ${schema.title ?? 'Model'}Schema = z.object({`];
  for (const [key, prop] of Object.entries(schema.properties || {})) {
    const zod = fieldZod(prop);
    const suffix = required.has(key) ? '' : '.optional()';
    lines.push(`  ${JSON.stringify(key)}: ${zod}${suffix},`);
  }
  lines.push('});', '');
  return lines.join('\n');
}

function main() {
  const files = fs.readdirSync(GEN_DIR).filter((f) => f.endsWith('.schema.json'));
  for (const file of files) {
    const full = path.join(GEN_DIR, file);
    const schema = JSON.parse(fs.readFileSync(full, 'utf-8'));
    const out = generate(schema);
    const target = full.replace('.schema.json', '.zod.ts');
    fs.writeFileSync(target, out);
    console.log(`wrote ${target}`);
  }
}

main();

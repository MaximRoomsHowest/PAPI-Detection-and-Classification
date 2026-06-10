/**
 * Static i18n key-usage scanner (third-pass audit).
 *
 * translations.test.js guarantees the four locales agree with each other —
 * but nothing guaranteed components reference keys that actually EXIST. A
 * leaf typo (`copy.live.provenanceTelemetryUnsed`) renders `undefined`
 * silently in every locale and no test went red.
 *
 * This test walks src/ for static dotted `copy.<group>.<...>` references and
 * asserts each resolves inside translations.en (parity covers the rest).
 * Scope is deliberately conservative:
 *  - comments are stripped first, so prose mentions don't count;
 *  - only chains whose first segment is a real top-level group are checked
 *    (an unrelated local variable named `copy` is ignored; a typo'd GROUP
 *    crashes visibly in dev anyway — `undefined.x` throws);
 *  - dynamic segments (`copy.states[id]`, `copy.live.angleSource?.[k]`)
 *    naturally truncate to their static prefix, which must still resolve.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { translations } from './translations'

const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const TOP_LEVEL_GROUPS = new Set(Object.keys(translations.en))
const KEY_PATTERN = /\bcopy\.([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)/g

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      walk(full, out)
    } else if (/\.(js|jsx)$/.test(name) && !/\.test\./.test(name)) {
      out.push(full)
    }
  }
  return out
}

function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
}

function resolves(path) {
  let node = translations.en
  for (const segment of path.split('.')) {
    if (typeof node === 'string') {
      // The key chain already resolved to a leaf string; the remaining
      // segments are String method calls (`.replace(...)`, `.toLowerCase()`).
      return true
    }
    if (node == null || typeof node !== 'object' || !(segment in node)) {
      return false
    }
    node = node[segment]
  }
  return node !== undefined
}

describe('i18n key usage', () => {
  it('every statically referenced copy.* key path exists in translations.en', () => {
    const missing = []
    for (const file of walk(SRC_ROOT)) {
      const source = stripComments(readFileSync(file, 'utf-8'))
      for (const match of source.matchAll(KEY_PATTERN)) {
        const path = match[1]
        if (!TOP_LEVEL_GROUPS.has(path.split('.')[0])) {
          continue // not an i18n reference (unrelated `copy` variable)
        }
        if (!resolves(path)) {
          missing.push(`${file.slice(SRC_ROOT.length + 1)} -> copy.${path}`)
        }
      }
    }
    expect(missing, `Undefined i18n key references:\n${missing.join('\n')}`).toEqual([])
  })

  it('the scanner actually sees component references (self-check)', () => {
    // Guards against the walker/regex silently matching nothing — a scanner
    // that scans nothing would pass forever.
    let hits = 0
    for (const file of walk(SRC_ROOT)) {
      const source = stripComments(readFileSync(file, 'utf-8'))
      for (const match of source.matchAll(KEY_PATTERN)) {
        if (TOP_LEVEL_GROUPS.has(match[1].split('.')[0])) hits += 1
      }
    }
    expect(hits).toBeGreaterThan(100)
  })
})

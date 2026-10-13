// Export Forgesteel's Draw Steel Heroes content as JSON.
//
// Run from inside a Forgesteel checkout, which is where its '@/' imports
// resolve:
//
//   npx tsx --tsconfig tsconfig.json /path/to/this/dump.ts /tmp/core.json
//
// Only Draw Steel: Heroes: it is the book covered by the Draw Steel Creator
// License. Forgesteel also carries third-party and community books, which are
// not. It splits Heroes in two - the rules in `core`, and the default
// setting in `orden` - and three of the book's twelve ancestries (hakaan,
// memonek, time raider) live in `orden`, so they are folded in here. Nothing
// else is taken from `orden`: its monsters are not in Heroes.
import { core } from '@/data/sourcebooks/official/core';
import { orden } from '@/data/sourcebooks/official/orden';
import { writeFileSync } from 'node:fs';

const heroes = { ...core, ancestries: [...core.ancestries, ...orden.ancestries] };

writeFileSync(process.argv[2] || 'core.json', JSON.stringify(heroes));

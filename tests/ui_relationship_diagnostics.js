// Offline DOM-free checks of the actual UI message function. No live/private state.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/ui_assets/app.js'), 'utf8');
const nodes = new Map();
const context = {
  document: {
    querySelector: () => ({content:'synthetic-token'}),
    querySelectorAll: () => [],
    getElementById: id => {
      if(!nodes.has(id))nodes.set(id, {});
      return nodes.get(id);
    }
  },
  // Leave initialization pending: tests exercise the real function, not a copied body.
  fetch: () => new Promise(() => {})
};
vm.createContext(context);
vm.runInContext(source, context);
const messages = flags => context.relationshipMessages({relationship:{features:flags}});
assert.equal(context.relationshipMessages({}).length, 0);
const negative = messages({negative_answer:true, negation_present:true});
assert(negative.some(s => s.includes('negative wording')));
assert(!negative.some(s => s.includes('Completed-event')));
assert(messages({planned_when_completed_requested:true}).some(s => s.includes('future-plan')));
assert(messages({temporal_conflict:true}).some(s => s.includes('Potential limitation')));
assert(messages({same_clause:true,completed_language:true}).some(s => s.includes('same clause')));
assert(!messages({unknown:'<script>inert()</script>'}).join('').includes('<script>'));
assert(source.includes('do not establish truth, evidence strength, or verification stance'));
console.log('UI relationship diagnostics: passed (negative, plan, conflict, partial and legacy cases).');

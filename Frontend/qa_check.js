const fs = require('fs');
const path = require('path');

function walk(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  list.forEach(file => {
    file = path.join(dir, file);
    const stat = fs.statSync(file);
    if (stat && stat.isDirectory()) { 
      results = results.concat(walk(file));
    } else if (file.endsWith('.html') || file.endsWith('.js')) { 
      results.push(file);
    }
  });
  return results;
}

const files = walk('app/templates');
files.push('app/static/js/main.js');

let allCalls = new Set();
let definedFuncs = new Set();

files.forEach(f => {
  const content = fs.readFileSync(f, 'utf8');
  
  // Find function definitions
  const defRegex = /function\s+([a-zA-Z0-9_]+)\s*\(/g;
  let match;
  while ((match = defRegex.exec(content)) !== null) {
    definedFuncs.add(match[1]);
  }
  const asyncDefRegex = /async\s+function\s+([a-zA-Z0-9_]+)\s*\(/g;
  while ((match = asyncDefRegex.exec(content)) !== null) {
    definedFuncs.add(match[1]);
  }
  const arrowRegex = /(const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(async\s*)?\(/g;
  while ((match = arrowRegex.exec(content)) !== null) {
    definedFuncs.add(match[2]);
  }

  // Find onclicks
  const onclickRegex = /on(?:click|submit)="([a-zA-Z0-9_]+)\(/g;
  while ((match = onclickRegex.exec(content)) !== null) {
    allCalls.add(JSON.stringify({ func: match[1], file: f }));
  }
});

definedFuncs.add('document.getElementById');
definedFuncs.add('event.preventDefault');
definedFuncs.add('event.stopPropagation');
definedFuncs.add('console.log');
definedFuncs.add('alert');
definedFuncs.add('setTimeout');
definedFuncs.add('navigator.clipboard.writeText');

console.log('Undefined functions called from HTML:');
allCalls.forEach(callStr => {
  const call = JSON.parse(callStr);
  if (!definedFuncs.has(call.func)) {
    console.log(`- ${call.func} in ${call.file}`);
  }
});

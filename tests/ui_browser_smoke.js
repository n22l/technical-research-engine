// Run in Codex's initialized cua_repl, with `tab` bound to the synthetic
// server at http://127.0.0.1:8001. No external browser dependencies required.
async function browserSmoke(tab) {
  const assert = (value, message) => { if (!value) throw Error(message); };
  assert((await tab.url()).startsWith('http://127.0.0.1:8001/'), 'Use the synthetic server');
  const page = tab.playwright;
  await page.locator('#question').fill('Test booster reflight occurred.');
  await page.locator('#research-button').press('Enter');
  await page.locator('select[name="relevant"]').waitFor({state:'visible',timeoutMs:15000});
  assert(!(await page.getByRole('button',{name:'Verify claim',exact:true}).isEnabled()), 'Review gate bypassed');
  const evidence = await page.locator('#run').innerText();
  assert(evidence.includes('<script>inert()</script>'), 'Literal source text missing');
  assert(!evidence.includes('SNIPPET_NOT_EVIDENCE'), 'Search snippet leaked into evidence');
  assert(await page.locator('#run script').count() === 0, 'Source HTML became executable');
  await page.locator('select[name="relevant"]').selectOption('true');
  await page.locator('select[name="stance"]').selectOption('SUPPORTS');
  await page.locator('select[name="strength"]').selectOption('DIRECT');
  await page.locator('input[name="reviewer"]').fill('Synthetic reviewer');
  await page.locator('textarea[name="rationale"]').fill('Fictional record directly establishes reflight.');
  await page.locator('input[name="material_scope_matches"]').press('Space');
  await page.getByText('Temporal, translation & maturity details',{exact:true}).press('Enter');
  await page.locator('select[name="status"]').selectOption('DEMONSTRATED');
  await page.locator('select[name="milestone"]').selectOption('reflight');
  await page.getByRole('button',{name:'Save',exact:true}).press('Enter');
  await page.getByText('All candidates reviewed. Engine eligibility checks still apply.',{exact:true}).waitFor({state:'visible'});
  await page.getByRole('button',{name:'Verify claim',exact:true}).press('Enter');
  await page.locator('#final-result').waitFor({state:'visible'});
  assert((await page.locator('#final-result .verdict').innerText()) === 'TRUE', 'Unexpected synthetic verdict');
  for (const format of ['JSON','MARKDOWN']) {
    await page.getByRole('button',{name:'Export '+format,exact:true}).press('Enter');
    const link = page.getByRole('link',{name:'Download '+format+' report',exact:true});
    await link.waitFor({state:'visible'});
    assert((await link.getAttribute('href')).startsWith('blob:'), 'Export payload unavailable');
    assert((await link.getAttribute('download')).endsWith(format === 'JSON' ? '.json' : '.md'), 'Wrong export filename');
  }
  await page.getByRole('button',{name:'History',exact:true}).press('Enter');
  await page.getByRole('button',{name:'Open research',exact:true}).waitFor({state:'visible'});
  await page.getByRole('button',{name:'Open research',exact:true}).press('Enter');
  await page.locator('#final-result').waitFor({state:'visible'});
  assert((await page.locator('#final-result .verdict').innerText()) === 'TRUE', 'History lost verdict');
  return 'PASS: review gate, inert evidence, saved review, verification, both export links, history';
}

const {test} = require('node:test');
const assert = require('node:assert/strict');
require('../app/static/interaction-utils.js');
const {debounce, mutationQueue, latestSearch} = globalThis.CinovelleUX;

test('debounce waits 300 ms and uses only the last input', context => {
  context.mock.timers.enable({apis:['setTimeout']});
  const calls = [];
  const search = debounce(value => calls.push(value));
  search('ci'); context.mock.timers.tick(200); search('cin');
  context.mock.timers.tick(299); assert.deepEqual(calls, []);
  context.mock.timers.tick(1); assert.deepEqual(calls, ['cin']);
  search('cancelled'); search.cancel(); context.mock.timers.tick(300);
  assert.deepEqual(calls, ['cin']);
});

test('mutations run in order and a failed request does not block the next', async () => {
  const queue = mutationQueue();
  const order = [];
  let release;
  const wait = new Promise(resolve => { release = resolve; });
  const first = queue(async () => { order.push('start'); await wait; order.push('end'); });
  const second = queue(() => { order.push('second'); throw new Error('network'); });
  const failure = assert.rejects(second, /network/);
  const third = queue(() => order.push('third'));
  await Promise.resolve(); assert.deepEqual(order, ['start']);
  release(); await first; await failure; await third;
  assert.deepEqual(order, ['start','end','second','third']);
});

test('late response cannot replace newer search results', async () => {
  const requests = [];
  const search = latestSearch((url, options) => new Promise(resolve => requests.push({url, options, resolve})));
  const received = [];
  const fail = error => { throw error; };
  const first = search.run('first', data => received.push(data), fail);
  const second = search.run('second', data => received.push(data), fail);
  assert.equal(requests[0].options.signal.aborted, true);
  requests[1].resolve({ok:true, json:async () => 'new'}); await second;
  requests[0].resolve({ok:true, json:async () => 'old'}); await first;
  assert.deepEqual(received, ['new']);
});

test('clearing input prevents pending search results and reports provider errors', async () => {
  let resolve;
  const received = [];
  const search = latestSearch(() => new Promise(done => { resolve = done; }));
  const running = search.run('x', data => received.push(data), error => received.push(error.message));
  search.cancel(); resolve({ok:true, json:async () => 'hidden'}); await running;
  assert.deepEqual(received, []);
  const errorSearch = latestSearch(async () => ({ok:false, json:async () => ({message:'rate limit'})}));
  await errorSearch.run('x', () => assert.fail(), error => received.push(error.message));
  assert.deepEqual(received, ['rate limit']);
});

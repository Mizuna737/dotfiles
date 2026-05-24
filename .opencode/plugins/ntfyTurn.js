/**
 * opencode plugin: send ntfy notification on turn completion
 * Fires on session.idle (agent finished responding, waiting for input)
 *
 * Requires env vars: NTFY_URL, NTFY_USER, NTFY_PASS
 * Falls back to empty -> no-op (won't break anything)
 */
module.exports = function (opencode) {
  var NTFY_URL = (process.env.NTFY_URL || '').replace(/\/$/, '');
  var NTFY_USER = process.env.NTFY_USER || '';
  var NTFY_PASS = process.env.NTFY_PASS || '';

  console.log('[ntfy] url=' + NTFY_URL + ' user=' + NTFY_USER + ' passLen=' + (NTFY_PASS ? NTFY_PASS.length : 0));

  if (!NTFY_URL || !NTFY_USER || !NTFY_PASS) {
    console.log('[ntfy] skipping — missing env vars');
    return { hooks: {} };
  }

  var spawn = require('child_process').spawn;

  function notify(msg) {
    spawn('curl', [
      '-s',
      '-u', NTFY_USER + ':' + NTFY_PASS,
      '-H', 'Title: opencode',
      '-H', 'Topic: opencode',
      '-H', 'Priority: high',
      '-d', msg,
      NTFY_URL + '/opencode'
    ], { timeout: 5000 });
  }

  return {
    hooks: {
      'session.idle': function (ctx) {
        var sid = ctx.session ? ctx.session.sessionId.substring(0, 8) : 'unknown';
        notify('opencode turn complete — ' + sid);
      }
    }
  };
};

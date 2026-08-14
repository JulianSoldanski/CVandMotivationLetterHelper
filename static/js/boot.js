// Kick everything off. Must load last: function declarations are hoisted
// only within their own file, so init() can only run once every other
// script has been evaluated.

init();

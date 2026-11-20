const config = require('./public/tailwind-config.js');
module.exports = { ...config, content: ['./app/**/*.{js,jsx}', './components/**/*.{js,jsx}'] };

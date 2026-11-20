module.exports = {
  reactStrictMode: false,
  distDir: process.env.NODE_ENV === 'development' ? '.next-dev' : '.next',
  poweredByHeader: false,
  devIndicators: false,
};

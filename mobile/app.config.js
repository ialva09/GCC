const appJson = require('./app.json');

module.exports = ({ config }) => ({
  ...appJson.expo,
  ...config,
  extra: {
    ...(appJson.expo.extra || {}),
    ...(config.extra || {}),
    expoProjectId: process.env.EXPO_PUBLIC_EXPO_PROJECT_ID
      || config.extra?.expoProjectId
      || 'REPLACE_WITH_EXPO_PROJECT_ID',
  },
});

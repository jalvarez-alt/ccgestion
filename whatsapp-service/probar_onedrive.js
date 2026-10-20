// Uso: npm run probar-onedrive   (después de completar GRAPH_* en .env)
const onedrive = require('./onedrive');

onedrive.probar()
  .then((pasos) => {
    pasos.forEach((p) => console.log('OK  ', p));
    console.log('\nOneDrive quedó conectado.');
  })
  .catch((e) => {
    console.error('FALLO', e.message);
    process.exit(1);
  });

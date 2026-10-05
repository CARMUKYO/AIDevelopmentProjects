import { openDatabase } from './db/connection.js';
import { migrate } from './db/migrate.js';
import { createApp } from './app.js';

const port = Number(process.env.PORT ?? 3000);
const db = openDatabase();
migrate(db);
createApp(db).listen(port, () => {
  console.log(`Todo API listening on http://localhost:${port}`);
});

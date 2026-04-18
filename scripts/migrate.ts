import fs from "node:fs/promises";
import path from "node:path";
import postgres from "postgres";

async function main() {
  const databaseUrl = process.env.DATABASE_URL;

  if (!databaseUrl) {
    throw new Error("DATABASE_URL is required for migrations.");
  }

  const sql = postgres(databaseUrl, { prepare: false });
  const migrationsDir = path.join(process.cwd(), "drizzle");
  const files = (await fs.readdir(migrationsDir))
    .filter((file) => file.endsWith(".sql"))
    .sort();

  await sql`
    create table if not exists schema_migrations (
      name text primary key,
      applied_at timestamptz not null default now()
    )
  `;

  const applied = await sql<{ name: string }[]>`select name from schema_migrations`;
  const appliedNames = new Set(applied.map((row) => row.name));

  for (const file of files) {
    if (appliedNames.has(file)) {
      continue;
    }

    const migration = await fs.readFile(path.join(migrationsDir, file), "utf8");

    await sql.begin(async (tx) => {
      await tx.unsafe(migration);
      await tx`insert into schema_migrations (name) values (${file})`;
    });
  }

  await sql.end();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

# Development stacks

Development-stack tasks combine the optional `fastapi` and `containers` tags. The bundled stack can run an application, debugger, PostgreSQL, Adminer, and Alembic migrator through Docker Compose.

Select the database addon before using database-specific tasks.

```toml
[tool.poe.env]
COMPOSE_TYPE = "fastapi"
COMPOSE_ADDONS = "db"
```

See [Development-stack settings](../configuration.md#development-stack-settings) for ports, compose overlays, and service configuration.

<!-- generated-task-reference -->

| Task | Description |
| - | - |
| [`stack-up`](reference/stack-up.md) | Bring up the development stack for the application. |
| [`stack-down`](reference/stack-down.md) | Bring down the development stack for the application. |
| [`reset-db`](reference/reset-db.md) | Reset the database by deleting the database volume. |
| [`run-db-migrations`](reference/run-db-migrations.md) | Run database migrations. |
| [`db-shell`](reference/db-shell.md) | Open a psql shell to the database container. |

<!-- end-generated-task-reference -->

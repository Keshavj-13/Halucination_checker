from backend.services.auth_store import DB_PATH, auth_store


def main() -> None:
    auth_store.ensure_default_admin()
    print(f"Initialized SQLite database at {DB_PATH}")


if __name__ == "__main__":
    main()

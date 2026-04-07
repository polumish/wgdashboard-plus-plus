import configparser
import os
import sqlite3
from sqlalchemy_utils import database_exists, create_database
from flask import current_app

def ConnectionString(database) -> str:
    parser = configparser.ConfigParser(strict=False)
    parser.read_file(open('wg-dashboard.ini', "r+"))
    sqlitePath = os.path.join("db")
    if not os.path.isdir(sqlitePath):
        os.mkdir(sqlitePath)
    if parser.get("Database", "type") == "postgresql":
        cn = f'postgresql+psycopg://{parser.get("Database", "username")}:{parser.get("Database", "password")}@{parser.get("Database", "host")}/{database}'
    elif parser.get("Database", "type") == "mysql":
        cn = f'mysql+pymysql://{parser.get("Database", "username")}:{parser.get("Database", "password")}@{parser.get("Database", "host")}/{database}'
    else:
        cn = f'sqlite:///{os.path.join(sqlitePath, f"{database}.db")}'
    try:
        if not database_exists(cn):
            create_database(cn)
    except Exception as e:
        current_app.logger.error("Database error. Terminating: %s", e)
        exit(1)

    # Enable WAL mode for SQLite to allow concurrent reads during writes
    if cn.startswith("sqlite"):
        db_file = cn.replace("sqlite:///", "")
        try:
            conn = sqlite3.connect(db_file)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.close()
        except Exception:
            pass

    return cn
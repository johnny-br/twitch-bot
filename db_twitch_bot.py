import sqlite3
from typing import List
import asyncio


class DB_Bot:
    def __init__(self, canal: str) -> None:
        self.canal = canal
        self.conn = sqlite3.connect(f"db_bot_{canal}.db")
        self.criaTabelas()

    def criaTabelas(self) -> None:

        self.conn.execute(
            """\
        CREATE TABLE IF NOT EXISTS mensagens
        (display_name TEXT, mod TEXT,subscriber TEXT,
        tmi_sent_ts INTEGER, user_id INTEGER, user_type TEXT, message TEXT)""",
        )

        self.conn.execute(
            """\
        CREATE TABLE IF NOT EXISTS mensagens_excluidas
        (display_name TEXT, tmi_sent_ts INTEGER, message TEXT)""",
        )

    async def insereMensagens(self, mensagens: List[tuple]) -> None:
        if mensagens:
            self.conn.executemany(
                """\
            INSERT INTO mensagens
            (display_name,mod,subscriber,tmi_sent_ts,
            user_id,user_type, message) VALUES (?, ?, ?,?, ?, ?,?)""",
                mensagens,
            )
            self.conn.commit()

    async def insereMensagensExcluidas(self, mensagens: List[tuple]) -> None:
        if mensagens:
            self.conn.executemany(
                """\
            INSERT INTO mensagens_excluidas
            (display_name,tmi_sent_ts,message) VALUES (?, ?, ?)""",
                mensagens,
            )
            self.conn.commit()

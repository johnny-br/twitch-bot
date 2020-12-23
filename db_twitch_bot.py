import sqlite3
from typing import List
import asyncio

class DB_Bot:

	def __init__(self, canal: str) -> None:
		self.canal = canal
		self.conn = sqlite3.connect(f'db_bot_{canal}.db')
		self.criaTabelas()

	def criaTabelas(self) -> None:

		self.conn.execute("""
		CREATE TABLE IF NOT EXISTS mensagens(
			display_name TEXT, mod TEXT,subscriber TEXT, 
			tmi_sent_ts INTEGER, user_id INTEGER, user_type TEXT, message TEXT
				)
			""", )

	async def insereMensagens(self, mensagens: List[tuple]) -> None:
		self.conn.executemany('''INSERT INTO mensagens (display_name,mod,subscriber,
			tmi_sent_ts,user_id,user_type, message) 
			VALUES (?, ?, ?,?, ?, ?,?)''', mensagens)
		self.conn.commit()
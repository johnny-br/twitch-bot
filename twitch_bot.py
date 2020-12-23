import requests
import websockets
import asyncio
import re
import time
import aiohttp
from typing import Union, List
from db_twitch_bot import DB_Bot


"""
Salva mensagens do chat de canais da twitch.
É necessário ter a autorização do seu usuário e o access token.
O access token pode ser gerado em https://twitchapps.com/tmi/
É possível acompanhar multiplos canais ao mesmo tempo.
"""


class Twitch_Bot:
    def __init__(self, nick: str, access_token: str, channel: str) -> None:
        # token_type=bearer
        self.access_token = access_token
        self.url = "wss://irc-ws.chat.twitch.tv:443"
        self.server = "irc.chat.twitch.tv"
        self.port = 6667
        self.nickname = nick
        self.channel = "#" + channel
        self.db = DB_Bot(channel)
        self._conectado = False
        self._buffer_mensagens: List[tuple] = list()

        # apos x segundos de chat inativo se desconecta do canal
        self.t = 5 * 60
        # quantas mensagens o canal recebe por minuto
        self.tempo = time.perf_counter()
        self.contador = 0
        self.msgs_pmin = 0.0

    @property
    def conectado(self) -> bool:
        return self._conectado

    @property
    def buffer_mensagens(self) -> list:
        return self._buffer_mensagens

    @staticmethod
    async def tokenValido(access_token: str) -> bool:
        url = "https://id.twitch.tv/oauth2/validate"
        headers = {"Authorization": "OAuth " + access_token}

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as response:
                if "client_id" in await response.text():
                    return True
                else:
                    return False

    def atualizaContador(self) -> None:
        # print(reply)
        if self.contador == 15:
            canal = self.channel[1:].upper()
            delta_tempo = time.perf_counter() - self.tempo
            msgs_pmin = 900 / delta_tempo
            print(f"{canal} está recebendo {msgs_pmin:.1f} msgs/min")
            self.msgs_pmin = msgs_pmin
            self.contador = 0
            self.tempo = time.perf_counter()
        else:
            self.contador += 1

    def msg_info(self, msg: str) -> dict:
        try:
            info = dict()
            pattern = re.compile(
                r"(?:^@)(.*?)(?:\s:)(.*?tv)\s(.*?)(?:\s#)(.*?)(?:\s:)(.*)"
            )
            grupos = re.match(pattern, msg)

            if grupos:
                for _ in grupos[1].split(";"):
                    info[_.split("=")[0]] = _.split("=")[1]

                info["command"] = grupos[3]
                info["channel"] = grupos[4]
                info["message"] = grupos[5]

            return info

        except Exception:
            return {}

    async def processaMensagem(self, mensagem: Union[str, bytes]) -> None:
        if isinstance(mensagem, str):
            if mensagem.startswith("PING"):
                await self.envia("PONG\n")
                print("PONG")

            elif "PRIVMSG" in mensagem:
                m = self.msg_info(mensagem)
                self._buffer_mensagens.append(
                    (
                        m["display-name"],
                        m["mod"],
                        m["subscriber"],
                        m["tmi-sent-ts"],
                        m["user-id"],
                        m["user-type"],
                        m["message"],
                    )
                )
                self.atualizaContador()

            elif mensagem.startswith(":"):
                if "HOSTTARGET" in mensagem:
                    pass

                elif self.nickname in mensagem:
                    if not self._conectado:
                        self._conectado = True
                        print(f"Conectado em {self.channel[1:].upper()}")

                elif ":tmi.twitch.tv CAP * ACK" in mensagem:
                    pass

                else:
                    print(mensagem)

            elif "ROOMSTATE" in mensagem:
                pass
            elif "USERNOTICE" in mensagem:
                pass
            elif "CLEARMSG" in mensagem:
                pass
            elif "CLEARCHAT" in mensagem:
                pass
            else:
                print(mensagem)

    async def envia(self, mensagem: str) -> None:
        await self.ws.send(mensagem)

    async def seConectaAoSocket(self) -> None:
        try:
            self.ws = await websockets.connect(self.url, ssl=True)
        except ConnectionRefusedError:
            pass

    async def seConectaAoCanal(self) -> None:
        await self.envia(f"CAP REQ :twitch.tv/tags\n")
        await self.envia(f"CAP REQ :twitch.tv/commands\n")
        await self.envia(f"PASS oauth:{self.access_token}\n")
        await self.envia(f"NICK {self.nickname}\n")
        await self.envia(f"JOIN {self.channel}\n")

    async def iniciaServidor(self) -> None:
        await self.seConectaAoSocket()
        await self.seConectaAoCanal()
        await self.aguardaMensagens()

    async def aguardaMensagens(self) -> None:
        while True:
            try:
                reply = await asyncio.wait_for(self.ws.recv(), timeout=self.t)

            except (
                asyncio.TimeoutError,
                websockets.exceptions.ConnectionClosed,
            ) as err:
                self._conectado = False
                print(f"Erro: {err}")
                # .close é idempotente
                await self.ws.close()
                print("Vou colocar essas mensagens no db ..um instantinho..")
                await self.db.insereMensagens(self._buffer_mensagens)
                break

            except (asyncio.exceptions.CancelledError):
                self._conectado = False
                print(f"CTRL+C")
                await self.ws.close()
                print("Vou colocar essas mensagens no db ..um instantinho..")
                await self.db.insereMensagens(self._buffer_mensagens)
                break
                # try:
                # 	pong = await self.ws.ping()
                # 	await asyncio.wait_for(pong, timeout=10)
                # 	logging.debug('Ping OK, mantendo a conexao...')
                # 	continue
                # except:
                # 	await asyncio.sleep(10)
                # 	break  # inner loop

            # ao receber mensagem
            await self.processaMensagem(reply)
            if len(self._buffer_mensagens) == 100:
                await self.db.insereMensagens(self._buffer_mensagens)
                self._buffer_mensagens = list()


def main() -> None:
    nick = ""
    access_token = ""
    canal = ""
    servidor = Twitch_Bot(nick, access_token, canal)

    try:
        asyncio.run(servidor.iniciaServidor())
    except KeyboardInterrupt:
        print("Tchau tchau")


if __name__ == "__main__":
    main()

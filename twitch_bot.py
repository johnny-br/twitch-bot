import requests
import websockets
import asyncio
import re
import time
import aiohttp
from typing import Union, List
from db_twitch_bot import DB_Bot


"""
Script que salva mensagens do chat de canais da twitch.
É necessário ter a autorização do seu usuário e o access token.
O access token pode ser gerado em https://twitchapps.com/tmi/
É possível acompanhar multiplos canais ao mesmo tempo.
"""


class Twitch_Bot:
    def __init__(self, nick: str, access_token: str, channel: str):
        # token_type=bearer
        self.access_token = access_token
        self.url = "wss://irc-ws.chat.twitch.tv:443"
        self.server = "irc.chat.twitch.tv"
        self.port = 6667
        self.nickname = nick
        self.channel = "#" + channel
        self.db = DB_Bot(channel)
        # se conectou com sucesso ao canal
        self._conectado = False
        # tá dando host
        self._hosting = False
        self._buff_mensagens: List[tuple] = list()
        self._buff_mensagens_excluidas: List[tuple] = list()

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
    def hosting(self) -> bool:
        return self._hosting

    @property
    def buffer_mensagens(self) -> list:
        return self._buff_mensagens

    @property
    def buffer_mensagens_excluidas(self) -> list:
        return self._buff_mensagens_excluidas

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

    async def salvaMensagens(self) -> None:
        await self.db.insereMensagens(self._buff_mensagens)
        await self.db.insereMensagensExcluidas(self._buff_mensagens_excluidas)
        self._buff_mensagens = list()
        self._buff_mensagens_excluidas = list()

    async def privmsg(self, m: str) -> None:
        try:
            mensagem = dict()
            pattern = re.compile(
                r"(?:^@)(.*?)(?:\s:)(.*?tv)\s(.*?)(?:\s#)(.*?)(?:\s:)(.*)"
            )
            grupos = re.match(pattern, m)

            if grupos:
                for _ in grupos[1].split(";"):
                    mensagem[_.split("=")[0]] = _.split("=")[1]

                mensagem["command"] = grupos[3]
                mensagem["channel"] = grupos[4]
                mensagem["message"] = grupos[5]

        except Exception:
            print(f"PRIVSM Exeption {Exception}")
            # logging.error()

        self._buff_mensagens.append(
            (
                mensagem["display-name"],
                mensagem["mod"],
                mensagem["subscriber"],
                mensagem["tmi-sent-ts"],
                mensagem["user-id"],
                mensagem["user-type"],
                mensagem["message"],
            )
        )

        self.atualizaContador()

    async def sub(self, m: str) -> None:
        pass

    async def userNotice(self, m: str) -> None:
        pass

    async def notice(self, m: str) -> None:
        print(f"Notice: {m}")

    async def hostTarget(self, m: str) -> None:
        # O canal pode eventualmente parar de ser host
        # e continuar streamando
        await self.salvaMensagens()
        self._hosting = True
        print(f"Host para #{m.split()[3][1:]}\nSaindo...")

    async def ping(self, m: str) -> None:
        await self.envia("PONG\n")
        print("PONG")

    async def clearmsg(self, m: str) -> None:
        valores = m.split(" ", 1)[0].split(";")
        display_name = valores[0].split("=")[1]
        tmi_sent_ts = int(valores[3].split("=")[1])
        mensagem = m.split(":", 3)[2]
        self._buff_mensagens_excluidas.append(
            (display_name, tmi_sent_ts, mensagem)
        )
        print(f"Clearmsg: {m}")

    async def clearChat(self, m: str) -> None:
        pass

    async def globalUserState(self, m: str) -> None:
        pass

    async def join(self, m: str) -> None:
        pass

    async def userState(self, m: str) -> None:
        print(f"Conectado em {m.split()[3].upper()}")
        self._conectado = True

    async def roomState(self, m: str) -> None:
        pass

    async def processaMensagem(self, msg: str) -> None:

        comandos_ignorados = [
            "CAP",
            "001",
            "002",
            "003",
            "004",
            "375",
            "372",
            "376",
            "353",
            "366",
        ]
        tabela_handlers = {
            "PRIVMSG": self.privmsg,
            "USERNOTICE": self.userNotice,
            "NOTICE": self.notice,
            "CLEARMSG": self.clearmsg,
            "GLOBALUSERSTATE": self.globalUserState,
            "JOIN": self.join,
            "USERSTATE": self.userState,
            "ROOMSTATE": self.roomState,
            "CLEARCHAT": self.clearChat,
            "PING": self.ping,
            "HOSTTARGET": self.hostTarget,
        }

        mensagens = msg.split("\n")

        for mensagem in mensagens:
            if mensagem:
                if mensagem.startswith(":"):
                    x = mensagem.split(" ", 3)
                    comando = x[1].upper().rstrip()
                elif mensagem.startswith("@"):
                    x = mensagem.split(" ", 3)
                    comando = x[2].upper().rstrip()
                elif mensagem.startswith("PING"):
                    comando = "PING"
                else:
                    print(f"Mensagem não reconhecida: {mensagem}")
                    comando = ""

                try:
                    await tabela_handlers[comando](mensagem)
                except KeyError:
                    if comando not in comandos_ignorados:
                        print(f"Comando não reconhecido: {comando}")
                except Exception as err:
                    print(f"{err}")

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
        while not self.hosting:
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
                print("Melhor colocar essas mensagens no db ...um instantinho")
                await self.salvaMensagens()
                break

            except (asyncio.exceptions.CancelledError):
                self._conectado = False
                print(f"CTRL+C")
                await self.ws.close()
                print("Melhor colocar essas mensagens no db ...um instantinho")
                await self.salvaMensagens()
                break
                # tenta se reconectar
                # try:
                # 	pong = await self.ws.ping()
                # 	await asyncio.wait_for(pong, timeout=10)
                # 	logging.debug('Ping OK, mantendo a conexao...')
                # 	continue
                # except:
                # 	await asyncio.sleep(10)
                # 	break  # inner loop

            # ao receber mensagem
            await self.processaMensagem(str(reply))
            if len(self._buff_mensagens) == 100:
                await self.salvaMensagens()


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

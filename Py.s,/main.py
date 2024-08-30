import asyncio
import random
from highrise import *
from highrise.models import *
from asyncio import run as arun
from threading import Thread
from highrise.__main__ import *
from emotes import*
import time
import json
import os
    

import asyncio
import random
import json
import os
import time
from typing import Literal
from collections import deque

class WordGame:
    def __init__(self, bot):
        self.bot = bot
        self.correct_guess_user = None
        self.players_scores = self.load_scores()
        self.players_ranks = self.load_ranks()
        self.current_word = ""
        self.current_word_display = ""
        self.rank_thresholds = {
            "Unranked": 50,
            "Bronz": 100,
            "Gümüş": 200,
            "Altın": 300,
            "Elmas": 400,
            "Efsane": 500
        }
        self.words = self.load_words()
        self.game_active = False
        self.ipuc_sure = 10  # İpucu verme süresi 10 saniye
        self.correct_word = False
        self.start_command_user = "s1lhoutte"  # Oda sahibinin kullanıcı adı
        self.ipuc_harfleri = set()
        self.game_task = None
        self.hint_provided_time = None
        self.start_time = None
        self.total_game_times = self.load_game_times()
        self.user_fastest_guess_times = self.load_fastest_guess_times()

        # Recent words listesi
        self.recent_words = deque(maxlen=50)  # 50 kelime saklayacak şekilde oluşturulmuş deque

        # Gold gönderim zamanlayıcıları
        self.gold_tip_interval = 45  # Her 45 saniyede bir kontrol
        self.gold_tip_amount = 10

        # Asenkron başlatma fonksiyonunu çağır
        asyncio.run(self.start_tasks())

    def load_words(self):
        words = []
        try:
            with open("words.txt", "r") as file:
                for line in file:
                    words.extend(line.strip().split(','))
        except Exception as e:
            print(f"Kelime listesi yüklenirken hata: {e}")
        return words

    async def start_tasks(self):
        # Start gold tasks asynchronously
        asyncio.create_task(self.start_gold_tasks())  # asyncio.get_event_loop().create_task yerine bu şekilde başlat

    async def on_chat(self, user: str, message: str):
        try:
            current_time = time.time()

            # Kullanıcı adını temizle
            clean_user = user.strip()  # '@' işareti olmadan kullanıcı adı

            if message.lower().startswith("start") and clean_user.lower() == self.start_command_user.lower():
                if not self.game_active:
                    await self.start_new_round()
                else:
                    await self.bot.highrise.chat("Oyun zaten aktif. Lütfen bitmesini bekleyin.")
            elif message.lower() == self.current_word.lower() and self.game_active:
                if self.correct_guess_user is None:
                    self.correct_word = True
                    self.correct_guess_user = clean_user
                    guess_time = current_time - self.start_time

                    # Toplam oyun süresini güncelle
                    if clean_user in self.total_game_times:
                        self.total_game_times[clean_user] += (current_time - self.start_time)
                    else:
                        self.total_game_times[clean_user] = (current_time - self.start_time)

                    # En hızlı tahmin süresini güncelle
                    if clean_user in self.user_fastest_guess_times:
                        self.user_fastest_guess_times[clean_user] = min(self.user_fastest_guess_times[clean_user], guess_time)
                    else:
                        self.user_fastest_guess_times[clean_user] = guess_time

                    await self.bot.highrise.chat(f"Tebrikler {clean_user}! Doğru kelimeyi buldunuz. Kelime: {self.current_word}")
                    await self.update_score(clean_user)
                    await self.end_round()
                else:
                    await self.bot.highrise.chat("Bu kelimeyi zaten biri doğru tahmin etti. Yeni kelime bekleyin.")
            elif message.lower().startswith("!rank"):
                await self.show_rank(clean_user)
            elif message.lower().startswith("!sıralama"):
                await self.show_leaderboard(clean_user)
            elif message.lower().startswith("!ranklar"):
                await self.show_rank_info(clean_user)
            elif message.lower().startswith("!istatistik"):
                # Komutu gönderen kullanıcının veya belirli bir kullanıcının istatistiklerini göster
                target_user = message.split(" ", 1)[1] if len(message.split(" ")) > 1 else clean_user
                await self.show_statistics(target_user)
            elif message.lower().startswith("!puanlarısıfırla"):
                # Kullanıcı adını temizle
                target_user = message.split(" ", 1)[1].strip() if len(message.split(" ")) > 1 else None
                if clean_user.lower() == self.start_command_user.lower():
                    if target_user:
                        await self.reset_user_score(target_user)
                    else:
                        await self.reset_all_scores()
                else:
                    await self.bot.highrise.chat("Bu komutu kullanma yetkiniz yok.")
        except Exception as e:
            print(f"Chat komutunda hata: {e}")
            await self.bot.highrise.chat("Bir hata oluştu. Lütfen tekrar deneyin.")

    async def start_new_round(self):
        if not self.words:
            await self.bot.highrise.chat("Kelime listesi boş. Oyunu başlatamıyorum.")
            return

        # Yeni kelime seç ve recent_words kontrol et
        available_words = [word for word in self.words if word not in self.recent_words]
        if not available_words:
            await self.bot.highrise.chat("Kelime listesi tükenmiş. Lütfen daha sonra tekrar deneyin.")
            return

        self.current_word = random.choice(available_words)
        self.add_word_to_recent(self.current_word)  # Kelimeyi recent_words listesine ekle
        self.current_word_display = "_" * len(self.current_word)
        self.ipuc_harfleri = set()
        self.correct_word = False
        self.correct_guess_user = None
        self.game_active = True
        self.hint_provided_time = None
        self.start_time = time.time()

        await self.bot.highrise.chat(f"Yeni bir kelime oyunu başladı! İlk ipucu: {self.current_word_display}")

        if self.game_task:
            self.game_task.cancel()
        self.game_task = asyncio.create_task(self.provide_hints())


    async def provide_hints(self):
        try:
            while not self.correct_word:
                if '_' in self.current_word_display:
                    indices = [i for i, letter in enumerate(self.current_word_display) if letter == '_']
                    if indices:
                        index = random.choice(indices)
                        self.current_word_display = (
                            self.current_word_display[:index] + self.current_word[index] + self.current_word_display[index + 1:]
                        )
                        await self.bot.highrise.chat(f"İpucu: {self.current_word_display}")
                        await asyncio.sleep(self.ipuc_sure)  # 10 saniye bekle

                    if '_' in self.current_word_display:
                        if self.current_word_display.count('_') == 2:
                            await self.bot.highrise.chat("Son ipucu verildi. 10 saniye sonra kelime açığa çıkacak ve daha fazla tahmin kabul edilmeyecek.")
                            await asyncio.sleep(10)
                            if not self.correct_word:
                                await self.bot.highrise.chat(f"Kelime: {self.current_word}")
                                await self.bot.highrise.chat("Oyun bitti! Kelimeyi doğru tahmin edemediniz.")
                                await self.end_round()
                                return
        except Exception as e:
            print(f"İpucu sağlama sırasında hata: {e}")
            await self.bot.highrise.chat("Bir hata oluştu. Lütfen tekrar deneyin.")
            await self.end_round()

    async def end_round(self):
        self.game_active = False
        await asyncio.sleep(15)  # 15 saniye bekle ve yeni oyuna başla
        await self.start_new_round()

    async def update_score(self, user):
        try:
            # Puan güncelleme
            if user in self.players_scores:
                self.players_scores[user] += 1
            else:
                self.players_scores[user] = 1

            # Puanları kaydet
            self.save_scores()

            # Puan ve sıralama güncelleme
            user_score = self.players_scores[user]  # Burada user_score tanımlanmış olacak
            await self.update_rank(user)

            # 50 ve 50'nin katlarına ulaştığında 10 gold gönder
            if user_score % 50 == 0:
                result = await self.bot.highrise.tip_user(user_id=self.bot.get_user_id(user), tip="gold_bar_10")
                if result == "success":
                    await self.bot.highrise.chat(f"{user}, 50 puanlık biriktirdiğiniz için 10 gold aldınız!")
                elif result == "insufficient_funds":
                    await self.bot.highrise.chat(f"{user}, gold gönderme işlemi yapılamadı. Yetersiz bakiye.")
                else:
                    await self.bot.highrise.chat(f"{user}, gold gönderme işlemi sırasında bilinmeyen bir hata oluştu.")
        except Exception as e:
            print(f"Puan güncellenirken hata: {e}")

    async def update_rank(self, user):
        try:
            user_score = self.players_scores.get(user, 0)
            new_rank = "Unranked"
            for rank, threshold in sorted(self.rank_thresholds.items(), key=lambda x: x[1], reverse=True):
                if user_score >= threshold:
                    new_rank = rank
                    break
            self.players_ranks[user] = new_rank
            self.save_ranks()

            # Rank atlama mesajı
            if user_score in {100, 200, 300, 400, 500}:
                await self.bot.highrise.chat(f"Tebrikler {user}, puanınız {user_score} oldu ve {new_rank} rütbesine yükseldiniz!")
        except Exception as e:
            print(f"Sıralama güncellenirken hata: {e}")

    async def show_rank(self, user):
        try:
            rank = self.players_ranks.get(user, "Unranked")
            await self.bot.highrise.chat(f"{user} sıralamanız: {rank}")
        except Exception as e:
            print(f"Rank gösterilirken hata: {e}")

    async def show_leaderboard(self, user):
        try:
            sorted_scores = sorted(self.players_scores.items(), key=lambda x: x[1], reverse=True)
            leaderboard = "\n".join([f"{i+1}. {player} - {score} puan" for i, (player, score) in enumerate(sorted_scores[:5])])

            # Kullanıcının sıralamasını ve puanını belirle
            user_score = self.players_scores.get(user, 0)
            user_rank = next((i + 1 for i, (u, _) in enumerate(sorted_scores) if u == user), len(sorted_scores) + 1)

            if len(sorted_scores) > 5:
                # İlk 5 oyuncu ve kullanıcının sıralamasını ekle
                leaderboard += f"\n\n{user_rank}. {user} - {user_score} puan"
            elif len(sorted_scores) > 0:
                # Eğer oyuncu sıralamanın ilk 5'indeyse, sadece onu göster
                leaderboard += f"\n\n{user_rank}. {user} - {user_score} puan"

            await self.bot.highrise.chat(f"Leaderboard:\n{leaderboard}")
        except Exception as e:
            print(f"Leaderboard gösterilirken hata: {e}")


    async def show_rank_info(self, user):
        try:
            rank_info = "\n".join([f"{rank}: {threshold} puan" for rank, threshold in self.rank_thresholds.items()])
            await self.bot.highrise.chat(f"Rank Bilgisi:\n{rank_info}")
        except Exception as e:
            print(f"Rank bilgisi gösterilirken hata: {e}")

    async def show_statistics(self, target_user):
        try:
            score = self.players_scores.get(target_user, 0)
            rank = self.players_ranks.get(target_user, "Unranked")

            # Sıralamayı hesapla
            sorted_scores = sorted(self.players_scores.items(), key=lambda x: x[1], reverse=True)
            user_rank = next((i + 1 for i, (u, _) in enumerate(sorted_scores) if u == target_user), len(sorted_scores) + 1)

            stats_message = (f"{target_user} istatistikleri:\n"
                             f"Puan: {score}\n"
                             f"Sıralamanız: {user_rank}\n"
                             f"Rank: {rank}")

            await self.bot.highrise.chat(stats_message)
        except Exception as e:
            print(f"İstatistikler gösterilirken hata: {e}")

    async def reset_user_score(self, user):
        try:
            if user in self.players_scores:
                self.players_scores[user] = 0
                self.save_scores()
                await self.bot.highrise.chat(f"{user} için puanlar sıfırlandı.")
            else:
                await self.bot.highrise.chat(f"{user} için puan bulunamadı.")
        except Exception as e:
            print(f"Puan sıfırlama sırasında hata: {e}")

    async def reset_all_scores(self):
        try:
            self.players_scores.clear()
            self.save_scores()
            await self.bot.highrise.chat("Tüm puanlar sıfırlandı.")
        except Exception as e:
            print(f"Tüm puanları sıfırlama sırasında hata: {e}")

    def load_scores(self):
        if os.path.exists("scores.json"):
            with open("scores.json", "r") as file:
                return json.load(file)
        return {}

    def save_scores(self):
        with open("scores.json", "w") as file:
            json.dump(self.players_scores, file)

    def load_ranks(self):
        if os.path.exists("ranks.json"):
            with open("ranks.json", "r") as file:
                return json.load(file)
        return {}

    def save_ranks(self):
        with open("ranks.json", "w") as file:
            json.dump(self.players_ranks, file)

    def load_game_times(self):
        if os.path.exists("game_times.json"):
            with open("game_times.json", "r") as file:
                return json.load(file)
        return {}

    def load_fastest_guess_times(self):
        if os.path.exists("fastest_guess_times.json"):
            with open("fastest_guess_times.json", "r") as file:
                return json.load(file)
        return {}

    async def start_gold_tasks(self):
        while True:
            await asyncio.sleep(self.gold_tip_interval)
            for user, score in self.players_scores.items():
                if score % 50 == 0:
                    result = await self.bot.highrise.tip_user(user_id=self.bot.get_user_id(user), tip="gold_bar_10")
                    if result == "success":
                        await self.bot.highrise.chat(f"{user}, 50 puanlık biriktirdiğiniz için 10 gold aldınız!")
                    elif result == "insufficient_funds":
                        await self.bot.highrise.chat(f"{user}, gold gönderme işlemi yapılamadı. Yetersiz bakiye.")
                    else:
                        await self.bot.highrise.chat(f"{user}, gold gönderme işlemi sırasında bilinmeyen bir hata oluştu.")

    def get_word(self):
        available_words = [word for word in self.words if word not in self.recent_words]
        if not available_words:
            return None
        return random.choice(available_words)

    def add_word_to_recent(self, word):
        if word in self.recent_words:
            self.recent_words.remove(word)  # Eğer kelime varsa önce kaldır
        self.recent_words.append(word)


    def remove_old_words_from_recent(self):
        # Eğer recent_words listesi 50'yi aşarsa, en eski kelimeleri çıkar
        while len(self.recent_words) > 50:
            self.recent_words.popleft()




















        

class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.user_emote_loops = {}  # Tanımlandığından emin olmalısınız
        self.word_game = WordGame(self)  # WordGame sınıfını başlatıyoruz

    async def on_chat(self, user: str, message: str):
        await self.word_game.on_chat(user, message)

    async def on_ready(self):
        # Bot hazır olduğunda başlangıçta herhangi bir işlem yapma
        pass

    async def send_gold_tip(self, user: str, amount: int):
        # Burada tip gönderme işlevini tanımlayın
        # Örneğin:
        await self.highrise.send_tip(user, amount)  # Yöntemi botun API'sına göre uy
        
        
        

        

    haricler = ["S1lhoutte","AslanLa","Aslan4Leon","nNazunaNanakus","tTogaHimiko","TOGAHIMIKOH",]

    async def on_emote(self, user: User, emote_id: str, receiver: User | None) -> None:
      print(f"{user.username} emoted: {emote_id}")

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        print("hi im alive?")
        await self.highrise.tg.create_task(self.highrise.teleport(
            session_metadata.user_id, Position(11, 0, 1, "FrontRight")))




    async def on_chat(self, user: User, message: str) -> None:
        """On a received room-wide chat."""    

        if message.lower().startswith("asdasd"):
          await self.highrise.send_emote("emote-kiss")

        isimler1 = [
            "\n1 - @AslanLeo",
  
        ]


        if message.lower().startswith("banlist"):
          await self.highrise.chat("\n".join(isimler1))



        message = message.lower()

        teleport_locations = {
            "vip": Position(15, 7.5, 0.),
            "kat1": Position(13.5, 11.0, 7.5),
            "zemin": Position(0., 0., 0.),
            "kus": Position(random.randint(0, 40), random.randint(0, 40), random.randint(0, 40)),
            "kus2": Position(random.randint(0, 40), random.randint(0, 40), random.randint(0, 40))
        }

        for location_name, position in teleport_locations.items():
            if message ==(location_name):
                try:
                    await self.teleport(user, position)
                except:
                    print("Teleporlanma sırasında hata oluştu")

        if message.lower().startswith("bvbnvvnv") and await self.is_user_allowed(user):
            target_username = message.split("@")[-1].strip()
            room_users = await self.highrise.get_room_users()
            user_info = next((info for info in room_users.content if info[0].username.lower() == target_username.lower()), None)

            if user_info:
                target_user_obj, initial_position = user_info
                task = asyncio.create_task(self.reset_target_position(target_user_obj, initial_position))

                if target_user_obj.id not in self.position_tasks:
                    self.position_tasks[target_user_obj.id] = []
                self.position_tasks[target_user_obj.id].append(task)

        elif message.lower().startswith("fghfdfr") and await self.is_user_allowed(user):
            target_username = message.split("@")[-1].strip()
            room_users = await self.highrise.get_room_users()
            target_user_obj = next((user_obj for user_obj, _ in room_users.content if user_obj.username.lower() == target_username.lower()), None)

            if target_user_obj:
                tasks = self.position_tasks.pop(target_user_obj.id, [])
                for task in tasks:
                    task.cancel()
                print(f"Breaking position monitoring loop for {target_username}")
            else:
                print(f"User {target_username} not found in the room.")

        if message.lower().startswith("qweqqweqrtys"):
            target_username = message.split("@")[-1].strip()
            await self.userinfo(user, target_username)


        if message.startswith("+x") or message.startswith("-x"):
            await self.adjust_position(user, message, 'x')
        elif message.startswith("+y") or message.startswith("-y"):
            await self.adjust_position(user, message, 'y')
        elif message.startswith("+z") or message.startswith("-z"):
            await self.adjust_position(user, message, 'z')


        allowed_commands = ["asdaftyhu"] 
        if any(message.lower().startswith(command) for command in allowed_commands) and await self.is_user_allowed(user):
            target_username = message.split("@")[-1].strip()


            if target_username not in self.haricler:
                await self.switch_users(user, target_username)
            else:
                print(f"{target_username} is in the exclusion list and won't be affected by the switch.")

        if                          message.lower().startswith("rtyretw") or message.lower().startswith("bhjdfdgdf"):
          target_username =         message.split("@")[-1].strip()
          await                     self.teleport_to_user(user, target_username)
        if await self.is_user_allowed(user) and message.lower().startswith("safasfsada"):
            target_username = message.split("@")[-1].strip()
            if target_username not in self.haricler:
                await self.teleport_user_next_to(target_username, user)
        if message.lower().startswith("--") and await self.is_user_allowed(user):
            parts = message.split()
            if len(parts) == 2 and parts[1].startswith("@"):
                target_username = parts[1][1:]
                target_user = None

                room_users = (await self.highrise.get_room_users()).content
                for room_user, _ in room_users:
                    if room_user.username.lower() == target_username and room_user.username.lower() not in self.haricler:
                        target_user = room_user
                        break

                if target_user:
                    try:
                        kl = Position(random.randint(0, 40), random.randint(0, 40), random.randint(0, 40))
                        await self.teleport(target_user, kl)
                    except Exception as e:
                        print(f"An error occurred while teleporting: {e}")
                else:
                    print(f"Kullanıcı adı '{target_username}' odada bulunamadı.")

        if message.lower() == "nfvdfh" or message.lower() == "mbvvnvn":
            if user.id not in self.kus:
                self.kus[user.id] = False

            if not self.kus[user.id]:
                self.kus[user.id] = True

                try:
                    while self.kus.get(user.id, False):
                        kl = Position(random.randint(0, 29), random.randint(0, 29), random.randint(0, 29))
                        await self.teleport(user, kl)

                        await asyncio.sleep(0.7)
                except Exception as e:
                    print(f"Teleport sırasında bir hata oluştu: {e}")

        if message.lower() == "vbnvbnv" or message.lower() == "xcvxcvc":
            if user.id in self.kus: 
                self.kus[user.id] = False

        if message.lower().startswith("xcvxcvxvxc") and await self.is_user_allowed(user):
            target_username = message.split("@")[-1].strip().lower()

            if target_username not in self.haricler:
                room_users = (await self.highrise.get_room_users()).content
                target_user = next((u for u, _ in room_users if u.username.lower() == target_username), None)

                if target_user:
                    if target_user.id not in self.is_teleporting_dict:
                        self.is_teleporting_dict[target_user.id] = True

                        try:
                            while self.is_teleporting_dict.get(target_user.id, False):
                                kl = Position(random.randint(0, 39), random.randint(0, 29), random.randint(0, 39))
                                await self.teleport(target_user, kl)
                                await asyncio.sleep(1)
                        except Exception as e:
                            print(f"An error occurred while teleporting: {e}")

                        self.is_teleporting_dict.pop(target_user.id, None)
                        final_position = Position(1.0, 0.0, 14.5, "FrontRight")
                        await self.teleport(target_user, final_position)


        if message.lower().startswith("xcvxxc") and await self.is_user_allowed(user):
            target_username = message.split("@")[-1].strip().lower()

            room_users = (await self.highrise.get_room_users()).content
            target_user = next((u for u, _ in room_users if u.username.lower() == target_username), None)

            if target_user:
                self.is_teleporting_dict.pop(target_user.id, None)


        if message.lower() == "sdgsdsdfsd" and await self.is_user_allowed(user):
            if self.following_user is not None:
                await self.highrise.chat("Şu anda başka birini takip ediyorum, sıranızı bekleyin.")
            else:
                await self.follow(user)

        if message.lower() == "ewrwrwerwr" and await self.is_user_allowed(user):
            if self.following_user is not None:
                await self.highrise.chat("Takip etmeyi bıraktım.")
                self.following_user = None
            else:
                await self.highrise.chat("Şu anda kimseyi takip etmiyorum.")

        if message.lower().startswith("ytutyutu") and await self.is_user_allowed(user):
            parts = message.split()
            if len(parts) != 2:
                return
            if "@s1lhoutte" not in parts[1]:
                username = parts[1]
            else:
                username = parts[1][1:]

            room_users = (await self.highrise.get_room_users()).content
            for room_user, pos in room_users:
                if room_user.username.lower() == username.lower():
                    user_id = room_user.id
                    break

            if "user_id" not in locals():
                return

            try:
                await self.highrise.moderate_room(user_id, "cvbcbc")
            except Exception as e:
                return



        message = message.strip().lower()
        user_id = user.id

        if message.startswith(""):
            emote_name = message.replace("", "").strip()
            if user_id in self.user_emote_loops and self.user_emote_loops[user_id] == emote_name:
                await self.stop_emote_loop(user_id)
            else:
                await self.start_emote_loop(user_id, emote_name)

        if message == "xcvxcvxcv" or message == "dsfsdfssdfs" or message == "0":
            if user_id in self.user_emote_loops:
                await self.stop_emote_loop(user_id)

        if message == "dsgsdf":
            if user_id not in self.user_emote_loops:
                await self.start_random_emote_loop(user_id)

        if message == "tryrref" or message == "vbnvnvb":
            if user_id in self.user_emote_loops:
                if self.user_emote_loops[user_id] == "kljhjljkl":
                    await self.stop_random_emote_loop(user_id)


        message = message.strip().lower()

        if "@" in message:
            parts = message.split("@")
            if len(parts) < 2:
                return

            emote_name = parts[0].strip()
            target_username = parts[1].strip()

            if emote_name in emote_mapping:
                response = await self.highrise.get_room_users()
                users = [content[0] for content in response.content]
                usernames = [user.username.lower() for user in users]

                if target_username not in usernames:
                    return

                user_id = next((u.id for u in users if u.username.lower() == target_username), None)
                if not user_id:
                    return

                await self.handle_emote_command(user.id, emote_name)
                await self.handle_emote_command(user_id, emote_name)


        for emote_name, emote_info in emote_mapping.items():
            if message.lower() == emote_name.lower():
                try:
                    emote_to_send = emote_info["value"]
                    await self.highrise.send_emote(emote_to_send, user.id)
                except Exception as e:
                    print(f"Error sending emote: {e}")


        if message.lower().startswith("yuıyt ") and await self.is_user_allowed(user):
            emote_name = message.replace("ıujkh ", "").strip()
            if emote_name in emote_mapping:
                emote_to_send = emote_mapping[emote_name]["value"]
                room_users = (await self.highrise.get_room_users()).content
                tasks = []
                for room_user, _ in room_users:
                    tasks.append(self.highrise.send_emote(emote_to_send, room_user.id))
                try:
                    await asyncio.gather(*tasks)
                except Exception as e:
                    error_message = f"Error sending emotes: {e}"
                    await self.highrise.send_whisper(user.id, error_message)
            else:
                await self.highrise.send_whisper(user.id, "Invalid emote name: {}".format(emote_name))


        message = message.strip().lower()

        try:
            if message.lstrip().startswith(("tyuytut")):
                response = await self.highrise.get_room_users()
                users = [content[0] for content in response.content]
                usernames = [user.username.lower() for user in users]
                parts = message[1:].split()
                args = parts[1:]

                if len(args) >= 1 and args[0][0] == "@" and args[0][1:].lower() in usernames:
                    user_id = next((u.id for u in users if u.username.lower() == args[0][1:].lower()), None)

                    if message.lower().startswith("floating"):
                        await self.highrise.send_emote("emote-telekinesis", user.id)
                        await self.highrise.send_emote("emote-gravity", user_id)
        except Exception as e:
            print(f"An error occurred: {e}")

        if message.startswith("rd") or message.startswith("cvbcc"):
            try:
                emote_name = random.choice(list(secili_emote.keys()))
                emote_to_send = secili_emote[emote_name]["value"]
                await self.highrise.send_emote(emote_to_send, user.id)
            except:
                print("Dans emote gönderilirken bir hata oluştu.")

        # Call the WordGame's on_chat function for handling game logic
        if self.word_game:
            await self.word_game.on_chat(user.username, message)

#Numaralı emotlar numaralı emotlar

    async def handle_emote_command(self, user_id: str, emote_name: str) -> None:
        if emote_name in emote_mapping:
            emote_info = emote_mapping[emote_name]
            emote_to_send = emote_info["value"]

            try:
                await self.highrise.send_emote(emote_to_send, user_id)
            except Exception as e:
                print(f"Error sending emote: {e}")


    async def start_emote_loop(self, user_id: str, emote_name: str) -> None:
        if emote_name in emote_mapping:
            self.user_emote_loops[user_id] = emote_name
            emote_info = emote_mapping[emote_name]
            emote_to_send = emote_info["value"]
            emote_time = emote_info["time"]

            while self.user_emote_loops.get(user_id) == emote_name:
                try:
                    await self.highrise.send_emote(emote_to_send, user_id)
                except Exception as e:
                    if "Target user not in room" in str(e):
                        print(f"{user_id} odada değil, emote gönderme durduruluyor.")
                        break
                await asyncio.sleep(emote_time)

    async def stop_emote_loop(self, user_id: str) -> None:
        if user_id in self.user_emote_loops:
            self.user_emote_loops.pop(user_id)



#paid emotes paid emotes paid emote

    async def emote_loop(self):
        while True:
            try:
                emote_name = random.choice(list(paid_emotes.keys()))
                emote_to_send = paid_emotes[emote_name]["value"]
                emote_time = paid_emotes[emote_name]["time"]

                await self.highrise.send_emote(emote_id=emote_to_send)
                await asyncio.sleep(emote_time)
            except Exception as e:
                print("Error sending emote:", e) 



#Ulti Ulti Ulti Ulti Ulti Ulti Ulti

    async def start_random_emote_loop(self, user_id: str) -> None:
        self.user_emote_loops[user_id] = "twerw"
        while self.user_emote_loops.get(user_id) == "rturtu":
            try:
                emote_name = random.choice(list(secili_emote.keys()))
                emote_info = secili_emote[emote_name]
                emote_to_send = emote_info["value"]
                emote_time = emote_info["time"]
                await self.highrise.send_emote(emote_to_send, user_id)
                await asyncio.sleep(emote_time)
            except Exception as e:
                print(f"Error sending random emote: {e}")

    async def stop_random_emote_loop(self, user_id: str) -> None:
        if user_id in self.user_emote_loops:
            del self.user_emote_loops[user_id]



  #Genel Genel Genel Genel Genel

    async def send_emote(self, emote_to_send: str, user_id: str) -> None:
        await self.highrise.send_emote(emote_to_send, user_id)



    async def on_whisper(self, user: User, message: str) -> None:
        """On a received room whisper."""
        if await self.is_user_allowed(user) and message.startswith(''):
            try:
                xxx = message[0:]
                await self.highrise.chat(xxx)
            except:
                print("error 3")

    async def is_user_allowed(self, user: User) -> bool:
        user_privileges = await self.highrise.get_room_privilege(user.id)
        return user_privileges.moderator or user.username in ["s1lhoutte"]

#gellllbbb

    async def moderate_room(
        self,
        user_id: str,
        action: Literal["tyrtet", "werwrwr", "fgfgd", " cvbf"],
        action_length: int | None = None,
    ) -> None:
        """Moderate a user in the room."""

    async def userinfo(self, user: User, target_username: str) -> None:
        user_info = await self.webapi.get_users(username=target_username, limit=1)

        if not user_info.users:
            await self.highrise.chat("Kullanıcı bulunamadı, lütfen geçerli bir kullanıcı belirtin")
            return

        user_id = user_info.users[0].user_id

        user_info = await self.webapi.get_user(user_id)

        number_of_followers = user_info.user.num_followers
        number_of_friends = user_info.user.num_friends
        country_code = user_info.user.country_code
        outfit = user_info.user.outfit
        bio = user_info.user.bio
        active_room = user_info.user.active_room
        crew = user_info.user.crew
        number_of_following = user_info.user.num_following
        joined_at = user_info.user.joined_at.strftime("%d/%m/%Y %H:%M:%S")

        joined_date = user_info.user.joined_at.date()
        today = datetime.now().date()
        days_played = (today - joined_date).days

        last_login = user_info.user.last_online_in.strftime("%d/%m/%Y %H:%M:%S") if user_info.user.last_online_in else "Son giriş bilgisi mevcut değil"

        await self.highrise.chat(f"""Kullanıcı adı: {target_username}\nTakipçi: {number_of_followers}\nArkadaş: {number_of_friends}\nOyuna Başlama: {joined_at}\nOyanma Süresi: {days_played}""")

    async def follow(self, user: User, message: str = ""):
        self.following_user = user  
        while self.following_user == user:
            room_users = (await self.highrise.get_room_users()).content
            for room_user, position in room_users:
                if room_user.id == user.id:
                    user_position = position
                    break
            if user_position is not None and isinstance(user_position, Position):
                nearby_position = Position(user_position.x + 1.0, user_position.y, user_position.z)
                await self.highrise.walk_to(nearby_position)

            await asyncio.sleep(0.5) 

    async def adjust_position(self, user: User, message: str, axis: str) -> None:
        try:
            adjustment = int(message[2:])
            if message.startswith("-"):
                adjustment *= -1

            room_users = await self.highrise.get_room_users()
            user_position = None

            for user_obj, user_position in room_users.content:
                if user_obj.id == user.id:
                    break

            if user_position:
                new_position = None

                if axis == 'x':
                    new_position = Position(user_position.x + adjustment, user_position.y, user_position.z, user_position.facing)
                elif axis == 'y':
                    new_position = Position(user_position.x, user_position.y + adjustment, user_position.z, user_position.facing)
                elif axis == 'z':
                    new_position = Position(user_position.x, user_position.y, user_position.z + adjustment, user_position.facing)
                else:
                    print
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"An error occurred during position monitoring: {e}")  
  
  
    async def run(self, room_id, token) -> None:
        await __main__.main(self, room_id, token)
    class WebServer():
        def __init__(self):
            self.app = Flask(__name__)
            @self.app.route('/')
            def index() -> str:
                return "Alive"
        def run(self) -> None:
            self.app.run(host='0.0.0.0', port=8080)
        def keep_alive(self):
            t = Thread(target=self.run)
            t.start()
        class RunBot():
            room_id = "66cb165f1805035e08ebf1c1"
            bot_token = "0b94738c3e83423e0c932fbfad371c534c09d5c29963e529dda2bafcedb3403e"
            bot_file = "main"
            bot_class = "Bot"
            def __init__(self) -> None:
                self.definitions = [
                    BotDefinition(
                        getattr(import_module(self.bot_file), self.bot_class)(),
                        self.room_id, self.bot_token)
                ] 
            def run_loop(self) -> None:
                while True:
                    try:
                        arun(main(self.definitions)) 
                    except Exception as e:
                        import traceback
                        print("Caught an exception:")
                        traceback.print_exc()
                        time.sleep(1)
                        continue
        if __name__ == "__main__":
            RunBot().run_loop()